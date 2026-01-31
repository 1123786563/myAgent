import abc
import time
from typing import List, Dict, Any
from logger import get_logger
from retry_utils import exponential_backoff

log = get_logger("BaseConnector")

class BaseConnector(metaclass=abc.ABCMeta):
    """
    [Optimization 2] API-First 插件化架构基类
    统一处理速率限制、重试及数据标准化
    """
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.rate_limit_delay = 1.0 # 默认间隔 1s

    @abc.abstractmethod
    def fetch_raw_data(self, since_time: str) -> List[Dict[str, Any]]:
        """从外部 API 获取原始数据"""
        pass

    @abc.abstractmethod
    def transform_to_ledger(self, raw_item: Dict[str, Any]) -> Dict[str, Any]:
        """将外部格式转化为 LedgerAlpha 标准分录格式"""
        pass

    def sync(self, since_time: str):
        log.info(f"开始同步外部数据: {self.service_name} | Since: {since_time}")
        try:
            # 使用带抖动的重试机制
            raw_data = self._fetch_with_retry(since_time)
            
            standardized_data = []
            for item in raw_data:
                standardized_data.append(self.transform_to_ledger(item))
                time.sleep(self.rate_limit_delay) # 保护外部 API
                
            log.info(f"同步完成: {self.service_name} | 共 {len(standardized_data)} 条记录")
            return standardized_data
        except Exception as e:
            log.error(f"外部同步失败: {self.service_name} | {e}")
            return []

    def _fetch_with_retry(self, since_time: str, max_retries=3):
        for i in range(max_retries):
            try:
                return self.fetch_raw_data(since_time)
            except Exception as e:
                if i < max_retries - 1:
                    wait_t = exponential_backoff(i)
                    log.warning(f"重试同步 {self.service_name} ({i+1}/{max_retries}) | 延迟 {wait_t:.1f}s")
                else:
                    raise e
