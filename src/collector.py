import time
import os
import queue
import threading
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

    def run(self):
        log.info(f"{self.name} 已启动...")
        process_timeout = ConfigManager.get("collector.process_timeout", 30)
        
        while not should_exit():
            try:
                self.db.update_heartbeat(self.name, "RUNNING")
                file_path = self.task_queue.get(timeout=5)
                
                # 优化点：引入超时控制逻辑 (Robustness)
                if self._should_process(file_path):
                    # 使用简单的线程装饰或直接执行，此处逻辑增强为内部计时
                    start_t = time.time()
                    self._process_file(file_path)
                    elapsed = time.time() - start_t
                    if elapsed > process_timeout:
                        log.warning(f"文件处理超时 ({elapsed:.1f}s): {file_path}")
                
                self.task_queue.task_done()
            except queue.Empty:
                self.db.update_heartbeat(self.name, "IDLE")
                continue
            except Exception as e:
                log.error(f"{self.name} 处理异常: {e}")
                self.db.update_heartbeat(self.name, f"ERROR: {str(e)[:50]}")
                time.sleep(1)

    def _should_process(self, file_path):
        """增量扫描逻辑：检查路径是否已在 DB 中"""
        try:
            with self.db.transaction() as conn:
                res = conn.execute("SELECT id FROM transactions WHERE file_path = ?", (file_path,)).fetchone()
                return res is None
        except:
            return True

    def _process_file(self, file_path):
        time.sleep(0.1) # 降低资源占用
        if not os.path.exists(file_path): return
        
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in self.allowed_exts: return
        
        # 优化点：多模态资产语义聚合框架 (F3.1.3)
        if ext in {'.jpg', '.jpeg', '.png'}:
            if self._is_asset_photo(file_path):
                log.info(f"检测到资产实物照片: {os.path.basename(file_path)}，启动多模态语义聚合...")
                self._analyze_multimodal_asset(file_path)
                # 照片资产处理后可继续作为普通单据入库，或者标记后跳过
        
        if os.path.getsize(file_path) < 100:
            return

        # 优化点：银行流水识别逻辑 (F3.1.2)
        if ext in {'.csv', '.xlsx'}:
            if "流水" in file_path or "statement" in file_path.lower():
                log.info(f"检测到银行流水文件: {os.path.basename(file_path)}，启动预记账转化...")
                self._parse_bank_statement(file_path)
                return

        # 混合哈希计算
        file_hash = calculate_file_hash(file_path)
        if not file_hash: return

        res = self.db.add_transaction(
            status="PENDING",
            source_type="MANUAL",
            file_path=file_path,
            file_hash=file_hash
        )
        if res:
            log.info(f"单据入库成功 ID={res}: {os.path.basename(file_path)}")

    def _parse_bank_statement(self, file_path):
        """
        解析银行流水文件并生成 pending_entries (影子分录)
        """
        try:
            # 优化点：引入生成器模式分片解析，防止大文件导致内存溢出
            import csv
            def row_generator(path):
                with open(path, mode='r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        yield row

            count = 0
            for row in row_generator(file_path):
                vendor = row.get('对方户名', '未知商户')
                try:
                    amount = float(row.get('金额', 0))
                except:
                    continue
                if amount == 0: continue
                
                self.db.add_pending_entry(
                    amount=abs(amount),
                    vendor_keyword=vendor,
                    source="BANK_STATEMENT",
                    raw_desc=f"来自流水文件: {os.path.basename(file_path)}"
                )
                count += 1
            log.info(f"流水解析完成，已转化 {count} 条影子分录。")
        except Exception as e:
            log.error(f"解析流水失败: {e}")

    def _is_asset_photo(self, file_path):
        """基于文件名或元数据初步判定是否为资产实物照片"""
        return "asset" in file_path.lower() or "资产" in file_path

    def _analyze_multimodal_asset(self, file_path):
        """
        多模态资产识别框架 (F3.1.3)
        此处为逻辑框架预留，后续对接 Gemini/OpenManus 强推理
        """
        # 1. 提取 EXIF 时间与地理位置
        # 2. 检索 5 分钟内同位置的其他照片
        # 3. 提交至 L2 推理层判定资产类型 (如：办公桌、服务器、车辆)
        pass

def scan_input_dir(input_dir, task_queue):
    """
    补偿性全量扫描：防止 watchdog 遗漏
    """
    log.info(f"执行全量补偿扫描: {input_dir}")
    for root, dirs, files in os.walk(input_dir):
        for file in files:
            full_path = os.path.join(root, file)
            task_queue.put(full_path)

def start_watching():
    input_dir = ConfigManager.get("path.input")
    os.makedirs(input_dir, exist_ok=True)
    
    task_queue = queue.Queue()
    stop_event = threading.Event()
    db = DBHelper()

    # 优化点：启动时执行一次全量扫描 (可配置)
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
    log.info(f"Collector 已启动，线程数: {worker_count}，补偿扫描间隔: {scan_interval}s")
    
    try:
        while not should_exit():
            db.update_heartbeat("Collector-Master", "ACTIVE")
            
            # 优化点：补偿扫描频率降低，仅作为兜底
            time.sleep(scan_interval)
            if should_exit(): break
            
            scan_input_dir(input_dir, task_queue)
            
            for i, w in enumerate(workers):
                if not w.is_alive():
                    log.warning(f"Worker-{i} 异常退出，正在重启...")
                    new_w = CollectorWorker(task_queue, i)
                    new_w.start()
                    workers[i] = new_w
    except Exception as e:
        log.error(f"Collector 主循环异常: {e}")
    finally:
        log.info("Collector 正在退出...")

if __name__ == "__main__":
    start_watching()
