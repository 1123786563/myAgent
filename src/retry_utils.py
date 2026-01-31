import time
from logger import get_logger

log = get_logger("RetryUtils")

def exponential_backoff(retries, base_delay=1, max_delay=60):
    """
    计算并执行指数退避延迟
    """
    delay = min(max_delay, base_delay * (2 ** retries))
    log.info(f"指数退避重试: 第 {retries+1} 次尝试，延迟 {delay}s")
    time.sleep(delay)
    return delay
