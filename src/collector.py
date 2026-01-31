import time
import os
import queue
import threading
import hashlib
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from db_helper import DBHelper
from logger import get_logger
from config_manager import ConfigManager
from utils import calculate_file_hash

from graceful_exit import should_exit, register_cleanup

log = get_logger("Collector")

class ReceiptHandler(FileSystemEventHandler):
    def __init__(self, task_queue):
        self.task_queue = task_queue

    def on_created(self, event):
        if not event.is_directory:
            self.task_queue.put(event.src_path)

class CollectorWorker(threading.Thread):
    def __init__(self, task_queue, worker_id):
        super().__init__(daemon=True, name=f"Worker-{worker_id}")
        self.task_queue = task_queue
        self.db = DBHelper()
        self.allowed_exts = {'.pdf', '.jpg', '.jpeg', '.png', '.csv', '.xlsx'}
        # [Optimization 1] 时空关联缓冲区 (Temporal-Spatial Buffer)
        self.batch_buffer = []
        self.last_buffer_flush = time.time()

    def run(self):
        log.info(f"{self.name} 已启动...")
        process_timeout = ConfigManager.get("collector.process_timeout", 30)
        
        while not should_exit():
            try:
                self.db.update_heartbeat(self.name, "RUNNING")
                try:
                    file_path = self.task_queue.get(timeout=2)
                    self.batch_buffer.append(file_path)
                except queue.Empty:
                    pass
                
                # 缓冲区满或超过 5 秒未刷新则处理 (F3.1.3)
                if self.batch_buffer and (len(self.batch_buffer) >= 5 or (time.time() - self.last_buffer_flush > 5)):
                    self._flush_buffer()
                
                if self.batch_buffer: # If still has items (not flushed yet), loop back
                    continue
                    
                self.db.update_heartbeat(self.name, "IDLE")
                time.sleep(1)
            except Exception as e:
                log.error(f"{self.name} 主循环异常: {e}")
                time.sleep(1)

    def _flush_buffer(self):
        if not self.batch_buffer: return
        log.info(f"正在处理时空关联批次 (Size: {len(self.batch_buffer)})")
        
        # [Optimization 1] 生成组 ID (Spatial-Temporal Aggregation)
        # 简单策略：同一个批次内的照片视为一个逻辑组
        group_id = f"SG-{int(time.time()/300)}-{hashlib.md5(str(self.batch_buffer).encode()).hexdigest()[:6]}"
        
        for path in self.batch_buffer:
            try:
                if self._should_process(path):
                    self._process_file(path, group_id=group_id)
                self.task_queue.task_done()
            except Exception as e:
                log.error(f"处理缓冲文件失败 {path}: {e}")
                
        self.batch_buffer.clear()
        self.last_buffer_flush = time.time()

    def _should_process(self, file_path):
        """增量扫描逻辑：检查路径是否已在 DB 中"""
        try:
            with self.db.transaction() as conn:
                res = conn.execute("SELECT id FROM transactions WHERE file_path = ?", (file_path,)).fetchone()
                return res is None
        except:
            return True

    def _process_file(self, file_path, group_id=None):
        import uuid
        trace_id = str(uuid.uuid4())
        
        time.sleep(0.1) # 降低资源占用
        if not os.path.exists(file_path): return
        
        # [Suggestion 10] 增加文件锁定检查
        try:
            with open(file_path, 'a'):
                pass
        except IOError:
            log.warning(f"文件正在被写入，跳过本次处理: {file_path}", extra={'trace_id': trace_id})
            return

        ext = os.path.splitext(file_path)[1].lower()
        if ext not in self.allowed_exts: return
        
        # [Optimization 1] 影子银企直连识别
        if ext in {'.csv', '.xlsx'} and any(kw in file_path.lower() for kw in ["流水", "statement", "bank"]):
            log.info(f"检测到银行流水文件: {os.path.basename(file_path)}，启动预记账转化...", extra={'trace_id': trace_id})
            self._parse_bank_statement(file_path)
            return

        if os.path.getsize(file_path) < 100:
            return

        # 优化点：项目维度解析
        tags = []
        parent_dir = os.path.basename(os.path.dirname(file_path))
        if parent_dir and parent_dir != "input":
            tags.append({"key": "project_id", "value": parent_dir})

        # 混合哈希计算
        file_hash = calculate_file_hash(file_path)
        if not file_hash: return

        # 入库
        res = self.db.add_transaction_with_tags(
            trace_id=trace_id,
            status="PENDING",
            source_type="MANUAL",
            file_path=file_path,
            file_hash=file_hash,
            group_id=group_id,
            tags=tags
        )
        if res:
            log.info(f"单据入库成功 ID={res} | Group={group_id} | Tags: {tags}", extra={'trace_id': trace_id})

    def _parse_bank_statement(self, file_path):
        try:
            import csv
            import pandas as pd
            
            # [Optimization 1] Load mapping from config
            mapping = ConfigManager.get("bank_mapping.default", {})
            col_vendor = mapping.get("vendor_col", "对方户名")
            col_amount = mapping.get("amount_col", "金额")
            encoding = mapping.get("encoding", "utf-8-sig")

            batch = []
            
            # Support both CSV and Excel
            ext = os.path.splitext(file_path)[1].lower()
            if ext == '.csv':
                df = pd.read_csv(file_path, encoding=encoding)
            else:
                df = pd.read_excel(file_path)
            
            # Normalize columns
            df.columns = [c.strip() for c in df.columns]
            
            if col_vendor not in df.columns or col_amount not in df.columns:
                log.warning(f"列名不匹配 (Need: {col_vendor}, {col_amount}). Found: {df.columns.tolist()}")
                return

            for _, row in df.iterrows():
                vendor = str(row.get(col_vendor, '未知商户')).strip()
                try:
                    # Clean amount string (remove currency symbols, commas)
                    amt_str = str(row.get(col_amount, 0)).replace(',', '').replace('¥', '')
                    amount = float(amt_str)
                except: 
                    continue
                
                if amount == 0: continue
                
                # Use absolute value for now, assuming bank statement mixes +/-
                batch.append({
                    "amount": abs(amount), 
                    "vendor_keyword": vendor, 
                    "source": "BANK_FLOW"
                })
                
                if len(batch) >= 50:
                    self.db.add_pending_entries_batch(batch)
                    batch = []
            
            if batch:
                self.db.add_pending_entries_batch(batch)
            log.info(f"流水解析完成: {os.path.basename(file_path)}")
        except Exception as e:
            log.error(f"解析流水失败: {e}")

def scan_input_dir(input_dir, task_queue):
    log.info(f"执行全量补偿扫描: {input_dir}")
    for root, dirs, files in os.walk(input_dir):
        for file in files:
            full_path = os.path.join(root, file)
            task_queue.put(full_path)

def start_watching():
    input_dir = ConfigManager.get("path.input")
    os.makedirs(input_dir, exist_ok=True)
    
    task_queue = queue.Queue()
    db = DBHelper()

    if ConfigManager.get("collector.initial_scan_enabled", True):
        scan_input_dir(input_dir, task_queue)

    workers = []
    worker_count = ConfigManager.get("collector.worker_threads", 2)
    for i in range(worker_count):
        w = CollectorWorker(task_queue, i)
        w.start()
        workers.append(w)

    event_handler = ReceiptHandler(task_queue)
    observer = Observer()
    observer.schedule(event_handler, input_dir, recursive=True)
    observer.start()
    register_cleanup(observer.stop)
    register_cleanup(observer.join)
    
    scan_interval = ConfigManager.get("intervals.collector_scan", 60)
    
    try:
        while not should_exit():
            db.update_heartbeat("Collector-Master", "ACTIVE")
            time.sleep(scan_interval)
            if should_exit(): break
            scan_input_dir(input_dir, task_queue)
    except Exception as e:
        log.error(f"Collector 主循环异常: {e}")
    finally:
        log.info("Collector 正在退出...")

if __name__ == "__main__":
    start_watching()
