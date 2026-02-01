import threading
import time
from contextlib import contextmanager
from core.config_manager import ConfigManager
from core.db_metrics import DBMetrics
from infra.logger import get_logger
import os
from dotenv import load_dotenv
import psycopg2
import psycopg2.extras

# 加载 .env 文件
load_dotenv()

class DBBase:
    """
    [Optimization Iteration PG Only] 基础数据库连接与事务管理 (仅支持 PostgreSQL)
    """
    _instance = None
    _lock = threading.Lock()
    _local = threading.local()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DBBase, cls).__new__(cls)
                cls._instance.db_type = "postgres"
                cls._instance.pg_config = {
                    "host": os.getenv("POSTGRES_HOST", "localhost"),
                    "port": os.getenv("POSTGRES_PORT", "5432"),
                    "user": os.getenv("POSTGRES_USER", "postgres"),
                    "password": os.getenv("POSTGRES_PASSWORD", "postgres"),
                    "dbname": os.getenv("POSTGRES_DBNAME", "ledger_alpha")
                }
                cls._instance._connection_count = 0
        return cls._instance

    def _get_conn(self):
        reused = True
        if not hasattr(self._local, "conn") or self._local.conn is None or self._local.conn.closed:
            reused = False
            try:
                conn = psycopg2.connect(**self.pg_config)
                # 默认使用 DictCursor 保持与之前 SQLite Row 类似的访问方式
                self._local.conn = conn
            except Exception as e:
                get_logger("DB").error(f"连接 PostgreSQL 失败: {e}")
                raise e

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
            with self._local.conn.cursor() as cur:
                cur.execute("SELECT 1")
            return True
        except Exception:
            return False

    @contextmanager
    def transaction(self, mode=None):
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
            conn = None
            try:
                conn = self._get_conn()
                # 兼容性包装：使用一个代理类来模拟 SQLite connection 的 behavior
                class ConnProxy:
                    def __init__(self, real_conn):
                        self._conn = real_conn
                    def execute(self, sql, params=()):
                        cur = self._conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
                        cur.execute(sql, params)
                        return cur
                    def cursor(self, *args, **kwargs):
                        return self._conn.cursor(*args, **kwargs)
                    def commit(self): return self._conn.commit()
                    def rollback(self): return self._conn.rollback()
                    def __getattr__(self, name): return getattr(self._conn, name)

                yield ConnProxy(conn)
                conn.commit()

                duration = time.perf_counter() - start_t
                duration_ms = duration * 1000
                is_slow = duration > slow_threshold
                DBMetrics.record_transaction(True, duration_ms, retries_used, is_slow)
                return
            except Exception as e:
                if conn:
                    try: conn.rollback()
                    except: pass
                last_error = e
                retries_used = i + 1
                
                # PG 的并发冲突通常是 serialization_failure 或 deadlock_detected
                if hasattr(e, 'pgcode') and e.pgcode in ('40001', '40P01'):
                    wait_time = (base_delay * (2 ** i)) + (random.random() * 0.1)
                    time.sleep(wait_time)
                    continue
                raise e

        duration = time.perf_counter() - start_t
        DBMetrics.record_transaction(False, duration * 1000, retries_used)
        if last_error: raise last_error
