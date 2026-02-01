"""
[Optimization Iteration 5] LLM Connector 单元测试
"""

import sys
import os
import unittest
import json

# 添加 src 目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from llm_connector import (
    LLMResponseCache,
    TokenBudgetManager,
    MockOpenManusLLM,
    LLMFactory
)


class TestLLMResponseCache(unittest.TestCase):
    """LLM 响应缓存测试"""

    def setUp(self):
        self.cache = LLMResponseCache(max_size=5, ttl_seconds=1)

    def test_cache_set_and_get(self):
        """基本的存取测试"""
        response = {"category": "技术服务费", "confidence": 0.95}
        self.cache.set("test prompt", "test-model", response)

        cached = self.cache.get("test prompt", "test-model")
        self.assertIsNotNone(cached)
        self.assertEqual(cached["category"], "技术服务费")

    def test_cache_miss(self):
        """缓存未命中测试"""
        cached = self.cache.get("nonexistent prompt", "test-model")
        self.assertIsNone(cached)

    def test_cache_key_isolation(self):
        """不同 prompt/model 组合隔离测试"""
        self.cache.set("prompt1", "model-a", {"result": "A"})
        self.cache.set("prompt1", "model-b", {"result": "B"})
        self.cache.set("prompt2", "model-a", {"result": "C"})

        self.assertEqual(self.cache.get("prompt1", "model-a")["result"], "A")
        self.assertEqual(self.cache.get("prompt1", "model-b")["result"], "B")
        self.assertEqual(self.cache.get("prompt2", "model-a")["result"], "C")

    def test_cache_ttl_expiration(self):
        """TTL 过期测试"""
        import time
        self.cache.set("expiring", "model", {"data": "test"})

        # 立即获取应该成功
        self.assertIsNotNone(self.cache.get("expiring", "model"))

        # 等待 TTL 过期
        time.sleep(1.1)
        self.assertIsNone(self.cache.get("expiring", "model"))

    def test_cache_lru_eviction(self):
        """LRU 淘汰测试"""
        # 填满缓存
        for i in range(5):
            self.cache.set(f"prompt-{i}", "model", {"index": i})

        # 所有条目都应该存在
        for i in range(5):
            self.assertIsNotNone(self.cache.get(f"prompt-{i}", "model"))

        # 添加第 6 个条目，应该淘汰最旧的
        self.cache.set("prompt-new", "model", {"index": "new"})

        # 新条目存在
        self.assertIsNotNone(self.cache.get("prompt-new", "model"))

    def test_cache_clear(self):
        """清空缓存测试"""
        self.cache.set("prompt", "model", {"data": "test"})
        self.cache.clear()
        self.assertIsNone(self.cache.get("prompt", "model"))


class TestTokenBudgetManager(unittest.TestCase):
    """Token 预算管理器测试"""

    def test_singleton_pattern(self):
        """单例模式测试"""
        manager1 = TokenBudgetManager()
        manager2 = TokenBudgetManager()
        self.assertIs(manager1, manager2)

    def test_check_budget_initially_allowed(self):
        """初始状态预算应该允许"""
        manager = TokenBudgetManager()
        # 重置计数器确保测试独立
        manager.daily_cost_usd = 0.0
        manager.monthly_cost_usd = 0.0

        allowed, reason = manager.check_budget()
        self.assertTrue(allowed)
        self.assertEqual(reason, "OK")

    def test_record_usage(self):
        """记录使用量测试"""
        manager = TokenBudgetManager()
        initial_tokens = manager.daily_tokens

        manager.record_usage(100, 50)

        self.assertEqual(manager.daily_tokens, initial_tokens + 150)

    def test_get_stats(self):
        """获取统计信息测试"""
        manager = TokenBudgetManager()
        stats = manager.get_stats()

        self.assertIn("daily_tokens", stats)
        self.assertIn("daily_cost_usd", stats)
        self.assertIn("monthly_tokens", stats)
        self.assertIn("request_count", stats)
        self.assertIn("cache_hit_rate", stats)


class TestMockOpenManusLLM(unittest.TestCase):
    """Mock LLM 测试"""

    def test_generate_response_structure(self):
        """响应结构测试"""
        llm = MockOpenManusLLM()
        response = llm.generate_response("Test with aliyun keyword")

        self.assertIn("reasoning", response)
        self.assertIn("result", response)
        self.assertIn("confidence", response)
        self.assertIn("category", response["result"])

    def test_keyword_matching(self):
        """关键词匹配测试"""
        llm = MockOpenManusLLM()

        # 测试已知关键词
        response = llm.generate_response("Payment to aliyun for cloud services")
        self.assertEqual(response["result"]["category"], "技术服务费")
        self.assertGreater(response["confidence"], 0.9)

    def test_unknown_vendor_low_confidence(self):
        """未知供应商低置信度测试"""
        llm = MockOpenManusLLM()
        response = llm.generate_response("Payment to random unknown vendor xyz123")

        self.assertLess(response["confidence"], 0.5)


class TestLLMFactory(unittest.TestCase):
    """LLM 工厂测试"""

    def test_get_mock_llm(self):
        """获取 Mock LLM 实例"""
        LLMFactory.reset()
        llm = LLMFactory.get_llm("MOCK")
        self.assertIsInstance(llm, MockOpenManusLLM)

    def test_singleton_caching(self):
        """单例缓存测试"""
        LLMFactory.reset()
        llm1 = LLMFactory.get_llm("MOCK")
        llm2 = LLMFactory.get_llm("MOCK")
        self.assertIs(llm1, llm2)

    def test_reset_clears_cache(self):
        """重置清除缓存测试"""
        llm1 = LLMFactory.get_llm("MOCK")
        LLMFactory.reset()
        llm2 = LLMFactory.get_llm("MOCK")
        self.assertIsNot(llm1, llm2)


class TestJSONParsing(unittest.TestCase):
    """JSON 解析逻辑测试"""

    def setUp(self):
        # 使用 Mock LLM 来测试，因为 OpenAICompatibleLLM 可能没有初始化
        from llm_connector import OpenAICompatibleLLM
        # 直接测试 _parse_response 方法
        self.llm = MockOpenManusLLM()

    def test_parse_direct_json(self):
        """直接 JSON 解析"""
        from llm_connector import OpenAICompatibleLLM
        llm = OpenAICompatibleLLM.__new__(OpenAICompatibleLLM)
        llm.__dict__.update({})  # 最小初始化

        content = '{"category": "技术服务费", "reason": "云服务", "confidence": 0.95}'
        result = llm._parse_response(content)

        self.assertEqual(result["category"], "技术服务费")
        self.assertEqual(result["confidence"], 0.95)

    def test_parse_markdown_json_block(self):
        """Markdown 代码块中的 JSON"""
        from llm_connector import OpenAICompatibleLLM
        llm = OpenAICompatibleLLM.__new__(OpenAICompatibleLLM)
        llm.__dict__.update({})

        content = '''Here is my analysis:
```json
{"category": "办公用品", "reason": "文具采购", "confidence": 0.88}
```
'''
        result = llm._parse_response(content)
        self.assertEqual(result["category"], "办公用品")

    def test_parse_embedded_json(self):
        """嵌入式 JSON"""
        from llm_connector import OpenAICompatibleLLM
        llm = OpenAICompatibleLLM.__new__(OpenAICompatibleLLM)
        llm.__dict__.update({})

        content = 'Based on my analysis: {"category": "差旅费", "reason": "交通", "confidence": 0.9} is my conclusion.'
        result = llm._parse_response(content)
        self.assertEqual(result["category"], "差旅费")

    def test_parse_failure_returns_default(self):
        """解析失败返回默认值"""
        from llm_connector import OpenAICompatibleLLM
        llm = OpenAICompatibleLLM.__new__(OpenAICompatibleLLM)
        llm.__dict__.update({})

        content = "This is not JSON at all, just plain text."
        result = llm._parse_response(content)

        self.assertEqual(result["category"], "待人工确认")
        self.assertEqual(result["confidence"], 0.3)


if __name__ == "__main__":
    unittest.main()
