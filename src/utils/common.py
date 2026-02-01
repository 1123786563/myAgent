import time
import functools
import hashlib
import os
from logger import get_logger

log = get_logger("Utils")

def timeit(func):
    """
    性能计时与异常自动捕获装饰器 (Suggestion 1)
    """
    import inspect
    if inspect.iscoroutinefunction(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                duration = time.perf_counter() - start_time
                if duration > 0.1:
                    log.warning(f"Async性能警告: {func.__name__} 耗时 {duration:.4f}s")
        return async_wrapper
    else:
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                duration = time.perf_counter() - start_time
                if duration > 0.1:
                    log.warning(f"Sync性能警告: {func.__name__} 耗时 {duration:.4f}s")
        return sync_wrapper

def trace_propagator(func):
    """
    [Suggestion 3] Trace ID 跨线程传递装饰器
    """
    import threading
    # 注意：logger 模块可能尚未完全加载其 threading.local，此处直接引用逻辑
    from logger import _context_data
    trace_id = getattr(_context_data, 'trace_id', 'Global')
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        from logger import log_context
        with log_context(trace_id):
            return func(*args, **kwargs)
    return wrapper

def singleton(cls):
    """
    单例模式装饰器
    """
    instances = {}
    @functools.wraps(cls)
    def get_instance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]
    return get_instance

def calculate_file_hash(file_path):
    """
    计算文件的MD5哈希值
    """
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception as e:
        log.error(f"计算文件哈希失败: {file_path}, 错误: {e}")
        return None
