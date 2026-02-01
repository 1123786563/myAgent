"""
[Optimization Iteration 4] 分布式追踪上下文管理

提供跨服务的请求追踪能力，确保 trace_id 在整个请求链路中传递。
"""

import uuid
import threading
import time
from typing import Optional, Dict, Any
from contextlib import contextmanager


class TraceContext:
    """
    线程本地的追踪上下文管理器

    使用示例:
        with TraceContext.start_trace() as ctx:
            # ctx.trace_id 在整个 with 块内可用
            do_something()

        # 或者手动管理
        trace_id = TraceContext.get_or_create_trace_id()
        TraceContext.set_attribute("user_id", "12345")
    """

    _local = threading.local()
    _stats = {
        "traces_created": 0,
        "spans_created": 0,
        "total_duration_ms": 0
    }
    _lock = threading.Lock()

    @classmethod
    def get_trace_id(cls) -> Optional[str]:
        """获取当前线程的 trace_id"""
        return getattr(cls._local, 'trace_id', None)

    @classmethod
    def get_or_create_trace_id(cls) -> str:
        """获取或创建 trace_id"""
        trace_id = cls.get_trace_id()
        if trace_id is None:
            trace_id = cls._generate_trace_id()
            cls._local.trace_id = trace_id
            cls._local.start_time = time.time()
            cls._local.attributes = {}
            cls._local.spans = []
            with cls._lock:
                cls._stats["traces_created"] += 1
        return trace_id

    @classmethod
    def set_trace_id(cls, trace_id: str):
        """设置 trace_id (用于从外部系统接收请求时)"""
        cls._local.trace_id = trace_id
        cls._local.start_time = time.time()
        cls._local.attributes = {}
        cls._local.spans = []

    @classmethod
    def clear(cls):
        """清除当前线程的追踪上下文"""
        if hasattr(cls._local, 'start_time'):
            duration = (time.time() - cls._local.start_time) * 1000
            with cls._lock:
                cls._stats["total_duration_ms"] += duration

        cls._local.trace_id = None
        cls._local.start_time = None
        cls._local.attributes = {}
        cls._local.spans = []

    @classmethod
    def set_attribute(cls, key: str, value: Any):
        """设置追踪属性"""
        if not hasattr(cls._local, 'attributes'):
            cls._local.attributes = {}
        cls._local.attributes[key] = value

    @classmethod
    def get_attribute(cls, key: str, default: Any = None) -> Any:
        """获取追踪属性"""
        attrs = getattr(cls._local, 'attributes', {})
        return attrs.get(key, default)

    @classmethod
    def get_all_attributes(cls) -> Dict[str, Any]:
        """获取所有追踪属性"""
        return getattr(cls._local, 'attributes', {}).copy()

    @classmethod
    @contextmanager
    def start_trace(cls, trace_id: Optional[str] = None):
        """
        启动一个新的追踪上下文

        Args:
            trace_id: 可选的外部 trace_id，如果不提供则自动生成
        """
        if trace_id:
            cls.set_trace_id(trace_id)
        else:
            cls.get_or_create_trace_id()

        try:
            yield cls
        finally:
            cls.clear()

    @classmethod
    @contextmanager
    def start_span(cls, name: str, attributes: Dict[str, Any] = None):
        """
        在当前追踪中创建一个 span (子操作)

        Args:
            name: span 名称
            attributes: span 属性
        """
        span_id = cls._generate_span_id()
        start_time = time.time()

        span = {
            "span_id": span_id,
            "name": name,
            "start_time": start_time,
            "attributes": attributes or {},
            "status": "OK"
        }

        if not hasattr(cls._local, 'spans'):
            cls._local.spans = []
        cls._local.spans.append(span)

        with cls._lock:
            cls._stats["spans_created"] += 1

        try:
            yield span
            span["status"] = "OK"
        except Exception as e:
            span["status"] = "ERROR"
            span["error"] = str(e)
            raise
        finally:
            span["duration_ms"] = (time.time() - start_time) * 1000

    @classmethod
    def get_spans(cls) -> list:
        """获取当前追踪的所有 spans"""
        return getattr(cls._local, 'spans', []).copy()

    @classmethod
    def get_stats(cls) -> Dict[str, Any]:
        """获取追踪统计信息"""
        with cls._lock:
            stats = cls._stats.copy()
        if stats["traces_created"] > 0:
            stats["avg_duration_ms"] = round(
                stats["total_duration_ms"] / stats["traces_created"], 2
            )
        return stats

    @staticmethod
    def _generate_trace_id() -> str:
        """生成 trace_id: 时间戳 + UUID"""
        timestamp = int(time.time() * 1000) % 1000000
        unique = uuid.uuid4().hex[:8]
        return f"T-{timestamp:06d}-{unique}"

    @staticmethod
    def _generate_span_id() -> str:
        """生成 span_id"""
        return uuid.uuid4().hex[:12]


def get_trace_id() -> Optional[str]:
    """便捷函数：获取当前 trace_id"""
    return TraceContext.get_trace_id()


def ensure_trace_id() -> str:
    """便捷函数：确保存在 trace_id"""
    return TraceContext.get_or_create_trace_id()
