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


class BankStatementParser:
    """
    [Optimization 2] Strategy Pattern for Bank Statement Parsing
    """

    def parse(self, df) -> list:
        raise NotImplementedError

    @classmethod
    def match(cls, columns) -> bool:
        return False


class AliPayParser(BankStatementParser):
    @classmethod
    def match(cls, columns):
        return "业务流水号" in columns and "对方名称" in columns

    def parse(self, df) -> list:
        batch = []
        for _, row in df.iterrows():
            try:
                # AliPay logic: check if outgoing
                if row.get("收/支", "") == "支出":
                    amt = float(str(row.get("金额", 0)).replace(",", ""))
                    vendor = str(row.get("对方名称", "Unknown")).strip()
                    batch.append(
                        {
                            "amount": abs(amt),
                            "vendor_keyword": vendor,
                            "source": "ALIPAY",
                        }
                    )
            except (ValueError, TypeError, KeyError) as e:
                log.debug(f"AliPay 行解析跳过: {e}")
                continue
        return batch


class WeChatParser(BankStatementParser):
    @classmethod
    def match(cls, columns):
        return "交易单号" in columns and "当前状态" in columns and "交易类型" in columns

    def parse(self, df) -> list:
        batch = []
        for _, row in df.iterrows():
            try:
                if row.get("收/支", "") == "支出":
                    # WeChat amounts often have '¥'
                    amt_str = (
                        str(row.get("金额(元)", 0)).replace("¥", "").replace(",", "")
                    )
                    amt = float(amt_str)
                    vendor = str(row.get("交易对方", "Unknown")).strip()
                    batch.append(
                        {
                            "amount": abs(amt),
                            "vendor_keyword": vendor,
                            "source": "WECHAT",
                        }
                    )
            except (ValueError, TypeError, KeyError) as e:
                log.debug(f"WeChat 行解析跳过: {e}")
                continue
        return batch


class GenericParser(BankStatementParser):
    """Fallback to config-based mapping"""

    def __init__(self):
        mapping = ConfigManager.get("bank_mapping.default", {})
        self.col_vendor = mapping.get("vendor_col", "对方户名")
        self.col_amount = mapping.get("amount_col", "金额")

    @classmethod
    def match(cls, columns):
        return True  # Always match as fallback

    def parse(self, df) -> list:
        batch = []
        if self.col_vendor not in df.columns or self.col_amount not in df.columns:
            return []

        for _, row in df.iterrows():
            try:
                vendor = str(row.get(self.col_vendor, "未知商户")).strip()
                amt_str = (
                    str(row.get(self.col_amount, 0)).replace(",", "").replace("¥", "")
                )
                amount = float(amt_str)
                if amount == 0:
                    continue

                batch.append(
                    {
                        "amount": abs(amount),
                        "vendor_keyword": vendor,
                        "source": "BANK_FLOW",
                    }
                )
            except (ValueError, TypeError, KeyError) as e:
                log.debug(f"Generic 行解析跳过: {e}")
                continue
        return batch


class CollectorWorker(threading.Thread):
    def __init__(self, task_queue, worker_id):
        super().__init__(daemon=True, name=f"Worker-{worker_id}")
        self.task_queue = task_queue
        self.db = DBHelper()
        self.allowed_exts = {".pdf", ".jpg", ".jpeg", ".png", ".csv", ".xlsx"}
        # [Iteration 8] 使用可配置的缓冲区参数
        self.batch_buffer = []
        self.last_buffer_flush = time.time()
        self.buffer_size = ConfigManager.get_int("collector.batch_buffer_size", 100)
        self.flush_interval = ConfigManager.get_int("collector.flush_interval", 30)
        self.min_file_size = ConfigManager.get_int("collector.min_file_size", 10)

    def run(self):
        log.info(f"{self.name} 已启动 (缓冲区: {self.buffer_size}, 刷新间隔: {self.flush_interval}s)...")
        process_timeout = ConfigManager.get("collector.process_timeout", 30)

        while not should_exit():
            try:
                self.db.update_heartbeat(self.name, "RUNNING")
                try:
                    file_path = self.task_queue.get(timeout=2)
                    self.batch_buffer.append(file_path)
                except queue.Empty:
                    pass

                # [Iteration 8] 使用可配置的缓冲区阈值
                if self.batch_buffer and (
                    len(self.batch_buffer) >= self.buffer_size
                    or (time.time() - self.last_buffer_flush > self.flush_interval)
                ):
                    self._flush_buffer()

                if self.batch_buffer:  # If still has items (not flushed yet), loop back
                    continue

                self.db.update_heartbeat(self.name, "IDLE")
                time.sleep(1)
            except Exception as e:
                log.error(f"{self.name} 主循环异常: {e}", exc_info=True)
                time.sleep(1)

    def _flush_buffer(self):
        if not self.batch_buffer:
            return
        log.info(f"正在处理时空关联批次 (Total Size: {len(self.batch_buffer)})")

        # [Optimization Round 2] 增强型多模态空间语义聚合 (SRS 3.1.3)
        # 逻辑：结合时间窗口、文件名相似度与内容指纹进行聚类

        # 1. 预处理：获取元数据
        file_meta = []
        for path in self.batch_buffer:
            try:
                stats = os.stat(path)
                # 简单视觉特征：文件名指纹（提取数字部分）
                visual_fingerprint = "".join(re.findall(r'\d+', os.path.basename(path)))
                file_meta.append({
                    "path": path,
                    "mtime": stats.st_mtime,
                    "size": stats.st_size,
                    "fingerprint": visual_fingerprint
                })
            except:
                file_meta.append({"path": path, "mtime": time.time(), "size": 0, "fingerprint": ""})

        # 2. 排序
        file_meta.sort(key=lambda x: x["mtime"])

        # 3. 深度聚类
        groups = []
        if file_meta:
            current_group = [file_meta[0]]
            for i in range(1, len(file_meta)):
                prev = current_group[-1]
                curr = file_meta[i]

                # 判定条件：时间间隔 < 30s OR 文件名指纹重合度高
                is_time_close = (curr["mtime"] - prev["mtime"]) < 30
                is_name_related = len(curr["fingerprint"]) > 3 and curr["fingerprint"][:4] == prev["fingerprint"][:4]

                if is_time_close or is_name_related:
                    current_group.append(curr)
                else:
                    groups.append(current_group)
                    current_group = [curr]
            groups.append(current_group)

        # 4. 执行入库
        for group in groups:
            # 生成组 ID (SG-时间-特征)
            group_id = f"SG-{int(group[0]['mtime'])}-{hashlib.md5(group[0]['path'].encode()).hexdigest()[:4]}"
            is_bundle = len(group) > 1
            
            if is_bundle:
                log.info(f"  [多模态聚合] 发现关联单据组 {group_id} (含 {len(group)} 个文件)")

            for item in group:
                path = item["path"]
                try:
                    if self._should_process(path):
                        # 注入聚合属性
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
                res = conn.execute(
                    "SELECT id FROM transactions WHERE file_path = ?", (file_path,)
                ).fetchone()
                return res is None
        except Exception as e:
            log.warning(f"检查文件处理状态失败: {e}")
            return True

    def _process_file(self, file_path, group_id=None):
        import uuid

        trace_id = str(uuid.uuid4())

        time.sleep(0.1)  # 降低资源占用
        if not os.path.exists(file_path):
            return

        # [Suggestion 10] 增加文件锁定检查
        try:
            with open(file_path, "a"):
                pass
        except IOError:
            log.warning(
                f"文件正在被写入，跳过本次处理: {file_path}",
                extra={"trace_id": trace_id},
            )
            return

        ext = os.path.splitext(file_path)[1].lower()
        if ext not in self.allowed_exts:
            return

        # [Optimization 1] 影子银企直连识别
        if ext in {".csv", ".xlsx"} and any(
            kw in file_path.lower() for kw in ["流水", "statement", "bank"]
        ):
            log.info(
                f"检测到银行流水文件: {os.path.basename(file_path)}，启动预记账转化...",
                extra={"trace_id": trace_id},
            )
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
        if not file_hash:
            return

        # 入库
        res = self.db.add_transaction_with_tags(
            trace_id=trace_id,
            status="PENDING",
            source_type="MANUAL",
            file_path=file_path,
            file_hash=file_hash,
            group_id=group_id,
            tags=tags,
        )
        if res:
            log.info(
                f"单据入库成功 ID={res} | Group={group_id} | Tags: {tags}",
                extra={"trace_id": trace_id},
            )

    def _parse_bank_statement(self, file_path):
        """
        [Optimization Iteration 3] 增强的银行流水解析
        - 更完善的编码检测
        - 详细的错误日志
        - 解析统计
        """
        import uuid
        trace_id = str(uuid.uuid4())[:8]

        try:
            import pandas as pd

            # Support both CSV and Excel
            ext = os.path.splitext(file_path)[1].lower()
            df = None
            encoding_used = None

            # [Optimization Iteration 3] 增强编码检测
            if ext == ".csv":
                encodings_to_try = ["utf-8-sig", "utf-8", "gbk", "gb2312", "gb18030", "latin-1"]
                for enc in encodings_to_try:
                    try:
                        df = pd.read_csv(file_path, encoding=enc)
                        encoding_used = enc
                        break
                    except (UnicodeDecodeError, pd.errors.ParserError):
                        continue
                    except Exception as e:
                        log.warning(f"尝试编码 {enc} 失败: {type(e).__name__}")
                        continue

                if df is None:
                    log.error(f"无法解析 CSV 文件，所有编码均失败: {file_path}", extra={"trace_id": trace_id})
                    return
            else:
                try:
                    df = pd.read_excel(file_path)
                    encoding_used = "excel"
                except Exception as e:
                    log.error(f"Excel 文件读取失败: {e}", extra={"trace_id": trace_id})
                    return

            log.info(f"文件读取成功 (编码: {encoding_used}): {os.path.basename(file_path)}", extra={"trace_id": trace_id})

            # Normalize columns
            df.columns = [str(c).strip() for c in df.columns]
            columns = set(df.columns)

            # [Optimization 2] Dynamic Parser Selection
            parser = None
            parser_name = "Unknown"
            if AliPayParser.match(columns):
                parser = AliPayParser()
                parser_name = "AliPay"
            elif WeChatParser.match(columns):
                parser = WeChatParser()
                parser_name = "WeChat"
            else:
                parser = GenericParser()
                parser_name = "Generic"

            log.info(f"使用解析器: {parser_name} | 文件: {os.path.basename(file_path)}", extra={"trace_id": trace_id})

            batch = parser.parse(df)

            if batch:
                self.db.add_pending_entries_batch(batch)
                log.info(f"流水解析完成: {len(batch)} 条记录已入库 | 解析器: {parser_name}", extra={"trace_id": trace_id})
            else:
                log.warning(f"未找到有效记录: {file_path} | 解析器: {parser_name}", extra={"trace_id": trace_id})

        except ImportError:
            log.error("pandas 库未安装，无法解析流水文件", extra={"trace_id": trace_id})
        except Exception as e:
            log.error(f"解析流水失败: {type(e).__name__}: {e}", extra={"trace_id": trace_id})


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
            if should_exit():
                break
            scan_input_dir(input_dir, task_queue)
    except Exception as e:
        log.error(f"Collector 主循环异常: {e}")
    finally:
        log.info("Collector 正在退出...")


if __name__ == "__main__":
    start_watching()
