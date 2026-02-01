import time
import random
from infra.logger import get_logger

log = get_logger("RetryUtils")

def exponential_backoff(retries, base_delay=1, max_delay=60, jitter=True):
    """
    [Suggestion 1] 增强型指数退避重试逻辑
    算法：Full Jitter (全随机抖动)
    原理：delay = random(0, min(max_delay, base_delay * 2^retries))
    """
    temp = min(max_delay, base_delay * (2 ** retries))
    
    if jitter:
        # 使用 Full Jitter 算法有效缓解竞争雪崩 (Contention)
        sleep_time = random.uniform(0, temp)
    else:
        sleep_time = temp
        
    log.info(f"指数退避重试 (Jitter={jitter}): 第 {retries+1} 次尝试，延迟 {sleep_time:.2f}s")
    time.sleep(sleep_time)
    return sleep_time
