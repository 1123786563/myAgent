import logging
import json
from infra.privacy_guard import PrivacyGuard

class PrivacyFilter(logging.Filter):
    """
    增强版日志脱敏过滤器：支持结构化数据脱敏、性能预检及环境感知
    """
    def __init__(self, level="STRICT"):
        super().__init__()
        self.guard = PrivacyGuard(role="AUDITOR" if level == "DEBUG" else "GUEST")
        self.level = level

    def filter(self, record):
        # 1. 处理消息内容
        record.msg = self._process_any(record.msg)
        
        # 2. 处理额外的结构化参数 (extra={...})
        if hasattr(record, 'args') and record.args:
            if isinstance(record.args, dict):
                record.args = self._process_any(record.args)
            elif isinstance(record.args, tuple):
                record.args = tuple(self._process_any(item) for item in record.args)
        
        return True

    def _process_any(self, data):
        """递归处理各种类型的数据结构"""
        if isinstance(data, str):
            # 性能预检：如果消息太短或不含可能敏感的特征，跳过正则
            if len(data) < 5: return data
            return self.guard.desensitize(data, context="LOG")
        
        elif isinstance(data, dict):
            return {k: self._process_any(v) for k, v in data.items()}
        
        elif isinstance(data, list):
            return [self._process_any(item) for item in data]
        
        elif isinstance(data, (int, float, bool)) or data is None:
            return data
            
        return str(data)

def apply_global_filter(logger, level="STRICT"):
    """
    便捷接口：为 logger 实例挂载隐私滤网
    """
    if not any(isinstance(f, PrivacyFilter) for f in logger.filters):
        logger.addFilter(PrivacyFilter(level=level))
