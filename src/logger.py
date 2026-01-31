import logging
import os
import queue
import threading
from contextlib import contextmanager
from logging.handlers import TimedRotatingFileHandler, QueueHandler, QueueListener
from config_manager import ConfigManager
from privacy_guard import PrivacyGuard
from logger_filter import PrivacyFilter

# 使用线程本地存储 Trace ID
_context_data = threading.local()

class PrivacyFilter(logging.Filter):
    """
    日志过滤器：确保所有输出日志均已脱敏
    """
    def __init__(self):
        super().__init__()
        self.guard = PrivacyGuard()

    def filter(self, record):
        if isinstance(record.msg, str):
            record.msg = self.guard.desensitize(record.msg)
        return True

class TraceFilter(logging.Filter):
    """
    Trace ID 过滤器：从上下文或 extra 中提取 trace_id
    """
    def filter(self, record):
        # 优先级：extra > context > default
        trace_id = getattr(record, 'trace_id', None)
        if trace_id is None:
            trace_id = getattr(_context_data, 'trace_id', 'Global')
        record.trace_id = trace_id
        return True

@contextmanager
def log_context(trace_id):
    """
    Trace ID 上下文管理器
    """
    old_id = getattr(_context_data, 'trace_id', None)
    _context_data.trace_id = trace_id
    try:
        yield
    finally:
        _context_data.trace_id = old_id

# 全局队列和监听器
_log_queue = queue.Queue(-1)
_listener = None

def get_logger(name):
    global _listener
    # 动态加载路径
    log_dir = ConfigManager.get("path.logs")
    os.makedirs(log_dir, exist_ok=True)
    
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        
        # 1. 设置主处理器
        file_handler = TimedRotatingFileHandler(
            os.path.join(log_dir, "ledger_alpha.log"),
            when="midnight",
            interval=1,
            backupCount=7,
            encoding='utf-8'
        )
        
        # [Suggestion 1] ERROR 级别独立存储
        error_file_handler = TimedRotatingFileHandler(
            os.path.join(log_dir, "ledger_alpha.error.log"),
            when="midnight",
            interval=1,
            backupCount=30,
            encoding='utf-8'
        )
        error_file_handler.setLevel(logging.ERROR)
        
        formatter = logging.Formatter('%(asctime)s [%(trace_id)s] - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        error_file_handler.setFormatter(formatter)
        
        file_handler.addFilter(PrivacyFilter())
        file_handler.addFilter(TraceFilter())
        error_file_handler.addFilter(PrivacyFilter())
        error_file_handler.addFilter(TraceFilter())
        
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.addFilter(PrivacyFilter())
        console_handler.addFilter(TraceFilter())
        
        # 2. 初始化监听器
        if _listener is None:
            # 增加 error_file_handler 到监听列表
            _listener = QueueListener(_log_queue, file_handler, error_file_handler, console_handler, respect_handler_level=True)
            _listener.start()
            # [Suggestion 2] 注册 atexit 钩子确保优雅退出
            import atexit
            atexit.register(stop_logging)
            
        # 3. 为 logger 添加 QueueHandler
        q_handler = QueueHandler(_log_queue)
        logger.addHandler(q_handler)
        
    return logger

def stop_logging():
    global _listener
    if _listener:
        _listener.stop()
        _listener = None
