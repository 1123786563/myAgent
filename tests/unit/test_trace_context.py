"""
[Optimization Iteration 5] TraceContext 单元测试
"""

import sys
import os
import unittest
import threading
import time

# 添加 src 目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from trace_context import TraceContext, get_trace_id, ensure_trace_id


class TestTraceContext(unittest.TestCase):
    """TraceContext 核心功能测试"""

    def setUp(self):
        """每个测试前清理上下文"""
        TraceContext.clear()

    def tearDown(self):
        """每个测试后清理上下文"""
        TraceContext.clear()

    def test_get_trace_id_returns_none_when_not_set(self):
        """未设置时返回 None"""
        self.assertIsNone(TraceContext.get_trace_id())

    def test_get_or_create_trace_id_creates_new_id(self):
        """自动创建新的 trace_id"""
        trace_id = TraceContext.get_or_create_trace_id()
        self.assertIsNotNone(trace_id)
        self.assertTrue(trace_id.startswith("T-"))

    def test_trace_id_format(self):
        """验证 trace_id 格式: T-{timestamp}-{uuid}"""
        trace_id = TraceContext.get_or_create_trace_id()
        parts = trace_id.split("-")
        self.assertEqual(len(parts), 3)
        self.assertEqual(parts[0], "T")
        self.assertEqual(len(parts[1]), 6)  # 6 位时间戳
        self.assertEqual(len(parts[2]), 8)  # 8 位 UUID

    def test_trace_id_persistence_in_thread(self):
        """同一线程中 trace_id 保持不变"""
        id1 = TraceContext.get_or_create_trace_id()
        id2 = TraceContext.get_or_create_trace_id()
        self.assertEqual(id1, id2)

    def test_set_trace_id(self):
        """手动设置 trace_id"""
        custom_id = "T-123456-abcdefgh"
        TraceContext.set_trace_id(custom_id)
        self.assertEqual(TraceContext.get_trace_id(), custom_id)

    def test_clear_removes_trace_id(self):
        """清除上下文后 trace_id 为 None"""
        TraceContext.get_or_create_trace_id()
        TraceContext.clear()
        self.assertIsNone(TraceContext.get_trace_id())

    def test_attributes_storage(self):
        """属性存储和获取"""
        TraceContext.get_or_create_trace_id()
        TraceContext.set_attribute("user_id", "12345")
        TraceContext.set_attribute("action", "classify")

        self.assertEqual(TraceContext.get_attribute("user_id"), "12345")
        self.assertEqual(TraceContext.get_attribute("action"), "classify")
        self.assertIsNone(TraceContext.get_attribute("nonexistent"))
        self.assertEqual(TraceContext.get_attribute("nonexistent", "default"), "default")

    def test_start_trace_context_manager(self):
        """上下文管理器测试"""
        with TraceContext.start_trace() as ctx:
            trace_id = TraceContext.get_trace_id()
            self.assertIsNotNone(trace_id)

        # 退出后应该被清理
        self.assertIsNone(TraceContext.get_trace_id())

    def test_start_trace_with_custom_id(self):
        """使用自定义 ID 启动追踪"""
        custom_id = "T-999999-testtest"
        with TraceContext.start_trace(trace_id=custom_id):
            self.assertEqual(TraceContext.get_trace_id(), custom_id)

    def test_span_creation(self):
        """Span 创建测试"""
        TraceContext.get_or_create_trace_id()

        with TraceContext.start_span("test_operation", {"key": "value"}) as span:
            self.assertEqual(span["name"], "test_operation")
            self.assertEqual(span["attributes"]["key"], "value")
            time.sleep(0.01)  # 模拟操作

        # Span 完成后应该有 duration
        self.assertIn("duration_ms", span)
        self.assertGreater(span["duration_ms"], 0)
        self.assertEqual(span["status"], "OK")

    def test_span_error_handling(self):
        """Span 错误处理测试"""
        TraceContext.get_or_create_trace_id()

        try:
            with TraceContext.start_span("failing_operation") as span:
                raise ValueError("Test error")
        except ValueError:
            pass

        self.assertEqual(span["status"], "ERROR")
        self.assertIn("Test error", span["error"])

    def test_thread_isolation(self):
        """多线程隔离测试"""
        results = {}

        def worker(thread_id):
            trace_id = TraceContext.get_or_create_trace_id()
            results[thread_id] = trace_id
            time.sleep(0.01)
            # 验证 ID 没有被其他线程覆盖
            self.assertEqual(TraceContext.get_trace_id(), trace_id)
            TraceContext.clear()

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 每个线程应该有不同的 trace_id
        trace_ids = list(results.values())
        self.assertEqual(len(set(trace_ids)), 5)

    def test_get_stats(self):
        """统计信息测试"""
        initial_stats = TraceContext.get_stats()
        initial_traces = initial_stats.get("traces_created", 0)

        TraceContext.get_or_create_trace_id()
        TraceContext.clear()

        stats = TraceContext.get_stats()
        self.assertEqual(stats["traces_created"], initial_traces + 1)


class TestConvenienceFunctions(unittest.TestCase):
    """便捷函数测试"""

    def setUp(self):
        TraceContext.clear()

    def tearDown(self):
        TraceContext.clear()

    def test_get_trace_id_function(self):
        """get_trace_id() 便捷函数"""
        self.assertIsNone(get_trace_id())
        TraceContext.get_or_create_trace_id()
        self.assertIsNotNone(get_trace_id())

    def test_ensure_trace_id_function(self):
        """ensure_trace_id() 便捷函数"""
        trace_id = ensure_trace_id()
        self.assertIsNotNone(trace_id)
        self.assertEqual(ensure_trace_id(), trace_id)


if __name__ == "__main__":
    unittest.main()
