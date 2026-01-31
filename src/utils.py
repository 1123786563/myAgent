import time
import functools
import hashlib
import os
from logger import get_logger

log = get_logger("Utils")

def timeit(func):
    """
    性能计时装饰器
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        duration = end_time - start_time
        if duration > 0.1: # 只记录耗时超过 100ms 的操作
            log.warning(f"性能警告: {func.__name__} 耗时 {duration:.4f}s")
        else:
            log.debug(f"{func.__name__} 耗时 {duration:.4f}s")
        return result
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
