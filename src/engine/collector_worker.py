import time
import os
import queue
import threading
import hashlib
import re
from core.db_helper import DBHelper
from infra.logger import get_logger
from core.config_manager import ConfigManager
from utils.common import calculate_file_hash
from infra.graceful_exit import should_exit
from engine.collector_parsers import AliPayParser, WeChatParser, GenericParser

log = get_logger("CollectorWorker")


class CollectorWorker(threading.Thread):
    def __init__(self, task_queue, worker_id):
        super().__init__(daemon=True, name=f"Worker-{worker_id}")
        self.task_queue = task_queue
        self.db = DBHelper()
        self.allowed_exts = {".pdf", ".jpg", ".jpeg", ".png", ".csv", ".xlsx"}
        self.batch_buffer = []
        self.last_buffer_flush = time.time()
        self.buffer_size = ConfigManager.get_int("collector.batch_buffer_size", 100)
        self.flush_interval = ConfigManager.get_int("collector.flush_interval", 30)
        self.min_file_size = ConfigManager.get_int("collector.min_file_size", 10)

    def run(self):
        while not should_exit():
            try:
                self.db.update_heartbeat(self.name, "RUNNING")
                try:
                    file_path = self.task_queue.get(timeout=2)
                    self.batch_buffer.append(file_path)
                except queue.Empty:
                    pass
                if self.batch_buffer and (
                    len(self.batch_buffer) >= self.buffer_size
                    or (time.time() - self.last_buffer_flush > self.flush_interval)
                ):
                    self._flush_buffer()
                if not self.batch_buffer:
                    self.db.update_heartbeat(self.name, "IDLE")
                time.sleep(1)
            except Exception as e:
                log.error(f"{self.name} exception: {e}")

    def _flush_buffer(self):
        if not self.batch_buffer:
            return
        file_meta = []
        for path in self.batch_buffer:
            try:
                stats = os.stat(path)
                # [Optimization Round 2] 提取更多元数据用于空间聚合
                fp = "".join(re.findall(r"\d+", os.path.basename(path)))
                size = stats.st_size
                file_meta.append(
                    {
                        "path": path,
                        "mtime": stats.st_mtime,
                        "fingerprint": fp,
                        "size": size,
                        "name": os.path.basename(path),
                    }
                )
            except:
                file_meta.append(
                    {
                        "path": path,
                        "mtime": time.time(),
                        "fingerprint": "",
                        "size": 0,
                        "name": "",
                    }
                )

        file_meta.sort(key=lambda x: x["mtime"])

        # [Optimization Round 2] 多模态空间语义聚合 (Multimodal Spatial Aggregation)
        # 识别时间接近、大小相近或名称模式一致的单据
        groups = []
        if file_meta:
            curr_g = [file_meta[0]]
            for i in range(1, len(file_meta)):
                item = file_meta[i]
                prev = curr_g[-1]

                time_diff = item["mtime"] - prev["mtime"]
                name_similarity = item["name"][:5] == prev["name"][:5]

                # 聚合逻辑：30秒内，或者文件名开头相同且10分钟内
                is_related = (time_diff < 30) or (name_similarity and time_diff < 600)

                if is_related:
                    curr_g.append(item)
                else:
                    groups.append(curr_g)
                    curr_g = [item]
            groups.append(curr_g)

        for group in groups:
            # 为聚合组生成唯一 ID
            group_id = f"SG-{int(group[0]['mtime'])}-{hashlib.md5(group[0]['path'].encode()).hexdigest()[:4]}"
            log.info(f"Detected document group {group_id} with {len(group)} files")
            for item in group:
                self._process_file(item["path"], group_id)
                self.task_queue.task_done()

        self.batch_buffer.clear()
        self.last_buffer_flush = time.time()

    def _process_file(self, path, group_id):
        if (
            not os.path.exists(path)
            or os.path.getsize(path) < self.min_file_size
            or os.path.basename(path).startswith(".")
        ):
            return

        file_hash = calculate_file_hash(path)

        try:
            with self.db.transaction() as session:
                from core.db_models import Transaction

                existing = (
                    session.query(Transaction)
                    .filter(
                        Transaction.file_hash == file_hash,
                        Transaction.status != "FAILED",
                    )
                    .first()
                )
                if existing:
                    log.warning(
                        f"Skipping duplicate file {os.path.basename(path)} (Hash: {file_hash[:8]}). Existing Trans ID: {existing.id}"
                    )
                    return
        except Exception as e:
            log.error(f"Deduplication check failed: {e}")

        ext = os.path.splitext(path)[1].lower()
        if ext not in self.allowed_exts:
            return
        if ext in {".csv", ".xlsx"} and any(
            kw in path.lower() for kw in ["流水", "statement", "bank"]
        ):
            self._parse_bank_statement(path)
            return

        tags = (
            [{"key": "project_id", "value": os.path.basename(os.path.dirname(path))}]
            if os.path.basename(os.path.dirname(path)) != "input"
            else []
        )
        self.db.add_transaction_with_tags(
            status="PENDING",
            source_type="MANUAL",
            file_path=path,
            file_hash=file_hash,
            group_id=group_id,
            tags=tags,
        )

    def _parse_bank_statement(self, path):
        try:
            import pandas as pd

            df = None
            if path.lower().endswith(".csv"):
                for enc in ["utf-8-sig", "utf-8", "gbk"]:
                    try:
                        df = pd.read_csv(path, encoding=enc)
                        break
                    except:
                        continue
            else:
                df = pd.read_excel(path)
            if df is None:
                return
            df.columns = [str(c).strip() for c in df.columns]
            cols = set(df.columns)
            parser = (
                AliPayParser()
                if AliPayParser.match(cols)
                else (WeChatParser() if WeChatParser.match(cols) else GenericParser())
            )
            batch = parser.parse(df)
            if batch:
                self.db.add_pending_entries_batch(batch)
        except Exception as e:
            log.error(f"Failed to parse bank statement {path}: {e}")
