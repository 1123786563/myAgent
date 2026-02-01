import sqlite3
import threading
import time
from contextlib import contextmanager
from core.config_manager import ConfigManager
from core.db_metrics import DBMetrics
from infra.logger import get_logger

class DBBase:
    """
    [Optimization Iteration 4] 基础数据库连接与事务管理
    """
    _instance = None
    _lock = threading.Lock()
    _local = threading.local()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DBBase, cls).__new__(cls)
                cls._instance.db_path = ConfigManager.get("path.db")
                cls._instance._connection_count = 0
                # _init_db should be called by the helper
        return cls._instance

    def _get_conn(self):
        reused = True
        if not hasattr(self._local, "conn") or self._local.conn is None:
            reused = False
            busy_timeout = ConfigManager.get_int("db.busy_timeout", 30000)
            journal_mode = ConfigManager.get_str("db.journal_mode", "WAL")

            conn = sqlite3.connect(
                self.db_path, 
                check_same_thread=False, 
                timeout=busy_timeout/1000,
                detect_types=sqlite3.PARSE_DECLTYPES
            )
            conn.row_factory = sqlite3.Row

            conn.execute(f"PRAGMA journal_mode={journal_mode}")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute("PRAGMA temp_store = MEMORY")
            conn.execute("PRAGMA mmap_size = 30000000000")
            conn.execute("PRAGMA cache_size = -64000")

            self._local.conn = conn
            self._local.statement_cache = {}
            self._local.last_health_check = time.time()

            with self._lock:
                self._connection_count += 1

        now = time.time()
        if now - getattr(self._local, 'last_health_check', 0) > 30:
            if not self._check_connection_health():
                self._local.conn = None
                DBMetrics.record_health_check(False)
                return self._get_conn()
            self._local.last_health_check = now
            DBMetrics.record_health_check(True)

        DBMetrics.record_connection(reused)
        return self._local.conn

    def _check_connection_health(self) -> bool:
        try:
            self._local.conn.execute("SELECT 1")
            return True
        except (sqlite3.OperationalError, sqlite3.InterfaceError, AttributeError):
            return False

    def _get_cursor(self, sql):
        conn = self._get_conn()
        if sql not in self._local.statement_cache:
            if len(self._local.statement_cache) > 100:
                self._local.statement_cache.pop(next(iter(self._local.statement_cache)))
            self._local.statement_cache[sql] = conn.cursor()
        return self._local.statement_cache[sql]

    @contextmanager
    def transaction(self, mode="DEFERRED"):
        retry_count = ConfigManager.get_int("db.retry_count", 5)
        base_delay = ConfigManager.get_float("db.retry_delay", 0.1)
        slow_threshold = ConfigManager.get_float("db.slow_threshold", 0.5)

        import random
        from infra.trace_context import TraceContext

        last_error = None
        start_t = time.perf_counter()
        retries_used = 0
        trace_id = TraceContext.get_trace_id()

        for i in range(retry_count):
            try:
                conn = self._get_conn()
                conn.execute(f"BEGIN {mode}")
                yield conn
                conn.commit()

                duration = time.perf_counter() - start_t
                duration_ms = duration * 1000
                is_slow = duration > slow_threshold

                DBMetrics.record_transaction(True, duration_ms, retries_used, is_slow)

                if is_slow:
                    get_logger("DB-Profiler").warning(
                        f"检测到慢事务耗时: {duration:.4f}s | Mode: {mode}",
                        extra={"trace_id": trace_id}
                    )
                return
            except sqlite3.OperationalError as e:
                last_error = e
                retries_used = i + 1
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    wait_time = (base_delay * (2 ** i)) + (random.random() * 0.1)
                    get_logger("DB").debug(
                        f"数据库锁等待，重试 {i+1}/{retry_count}，等待 {wait_time:.2f}s",
                        extra={"trace_id": trace_id}
                    )
                    time.sleep(wait_time)
                    continue
                raise e
            except Exception as e:
                try:
                    self._get_conn().rollback()
                except:
                    pass
                duration = time.perf_counter() - start_t
                DBMetrics.record_transaction(False, duration * 1000, retries_used)
                raise e

        duration = time.perf_counter() - start_t
        DBMetrics.record_transaction(False, duration * 1000, retries_used)
        if last_error:
            raise last_error

    def trigger_wal_checkpoint(self):
        try:
            conn = self._get_conn()
            conn.execute("PRAGMA wal_checkpoint(FULL)")
            get_logger("DB").debug("WAL 检查点执行成功 (FULL)")
            return True
        except Exception as e:
            get_logger("DB").error(f"WAL 检查点执行失败: {e}")
            return False

    def get_connection_stats(self) -> Dict[str, Any]:
        return {
            "total_connections_created": self._connection_count,
            "db_path": self.db_path,
            **DBMetrics.get_stats()
        }
