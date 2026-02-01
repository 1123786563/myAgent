import threading
import time
from contextlib import contextmanager
from core.config_manager import ConfigManager
from core.db_metrics import DBMetrics
from core.db_models import SessionLocal, engine, Base
from infra.logger import get_logger
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text

class DBBase:
    """
    [Optimization Iteration SQLAlchemy] 基础数据库连接与事务管理
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DBBase, cls).__new__(cls)
                # 预热连接池
                try:
                    with engine.connect() as conn:
                        conn.execute(text("SELECT 1"))
                except Exception as e:
                    get_logger("DB").error(f"数据库预热失败: {e}")
        return cls._instance

    @contextmanager
    def transaction(self, mode=None):
        retry_count = ConfigManager.get_int("db.retry_count", 5)
        base_delay = ConfigManager.get_float("db.retry_delay", 0.1)
        slow_threshold = ConfigManager.get_float("db.slow_threshold", 0.5)

        import random
        from infra.trace_context import TraceContext

        session = SessionLocal()
        start_t = time.perf_counter()
        retries_used = 0
        
        try:
            for i in range(retry_count):
                try:
                    yield session
                    session.commit()
                    
                    duration = time.perf_counter() - start_t
                    duration_ms = duration * 1000
                    is_slow = duration > slow_threshold
                    DBMetrics.record_transaction(True, duration_ms, retries_used, is_slow)
                    return
                except SQLAlchemyError as e:
                    session.rollback()
                    retries_used = i + 1
                    
                    # 检查是否为死锁或序列化失败，通常 SQLAlchemy 会封装原始错误
                    orig = getattr(e, 'orig', None)
                    if orig and hasattr(orig, 'pgcode') and orig.pgcode in ('40001', '40P01'):
                        wait_time = (base_delay * (2 ** i)) + (random.random() * 0.1)
                        time.sleep(wait_time)
                        continue
                    raise e
        finally:
            session.close()

    def _execute(self, query, params=None):
        """兼容旧版的快速执行方法"""
        with self.transaction() as session:
            if isinstance(query, str):
                result = session.execute(text(query), params or {})
            else:
                result = session.execute(query, params or {})
            return result
