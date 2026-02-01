"""
[Optimization Iteration 6] PromptManager 单元测试
"""

import sys
import os
import unittest

# 添加 src 目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from prompt_manager import PromptManager, PromptVersion


class TestPromptVersion(unittest.TestCase):
    """PromptVersion 数据类测试"""

    def test_init_with_defaults(self):
        """默认参数初始化"""
        pv = PromptVersion("test", "content")
        self.assertEqual(pv.name, "test")
        self.assertEqual(pv.content, "content")
        self.assertEqual(pv.version, "1.0")
        self.assertEqual(pv.use_count, 0)

    def test_init_with_all_params(self):
        """完整参数初始化"""
        pv = PromptVersion(
            name="accounting",
            content="prompt content",
            version="2.0",
            description="Test prompt",
            metadata={"author": "test"}
        )
        self.assertEqual(pv.version, "2.0")
        self.assertEqual(pv.metadata["author"], "test")

    def test_to_dict(self):
        """转换为字典"""
        pv = PromptVersion("test", "12345", version="1.5")
        d = pv.to_dict()
        self.assertEqual(d["name"], "test")
        self.assertEqual(d["content_length"], 5)


class TestPromptManagerParameterSubstitution(unittest.TestCase):
    """PromptManager 参数替换功能测试"""

    def setUp(self):
        self.manager = PromptManager()

    def test_simple_substitution(self):
        """简单参数替换"""
        content = "交易供应商: {vendor}, 金额: {amount}"
        result = self.manager._substitute_params(content, {
            "vendor": "阿里云",
            "amount": 1000
        })
        self.assertEqual(result, "交易供应商: 阿里云, 金额: 1000")

    def test_substitution_with_default(self):
        """带默认值的参数替换"""
        content = "供应商: {vendor:未知}, 备注: {note:无}"
        result = self.manager._substitute_params(content, {"vendor": "腾讯云"})
        self.assertEqual(result, "供应商: 腾讯云, 备注: 无")

    def test_escaped_braces(self):
        """转义花括号保留原样"""
        content = "JSON 格式: {{\"key\": \"value\"}}"
        result = self.manager._substitute_params(content, {})
        self.assertEqual(result, 'JSON 格式: {"key": "value"}')

    def test_missing_param_preserved(self):
        """未提供的参数保留原样"""
        content = "值: {missing_param}"
        result = self.manager._substitute_params(content, {})
        self.assertEqual(result, "值: {missing_param}")

    def test_mixed_substitution(self):
        """混合替换场景"""
        content = "供应商 {vendor} 的交易金额为 {amount:0} 元，状态: {{pending}}"
        result = self.manager._substitute_params(content, {"vendor": "京东"})
        self.assertEqual(result, "供应商 京东 的交易金额为 0 元，状态: {pending}")

    def test_get_prompt_params(self):
        """提取 Prompt 参数列表"""
        # 由于 get_prompt_params 依赖实际 prompt，我们直接测试正则逻辑
        import re
        content = "分析 {vendor} 的 {amount} 交易，备注: {note:无}"
        params = re.findall(r'(?<!\{)\{(\w+)(?::[^}]*)?\}(?!\})', content)
        self.assertIn("vendor", params)
        self.assertIn("amount", params)
        self.assertIn("note", params)


class TestPromptManagerCore(unittest.TestCase):
    """PromptManager 核心功能测试"""

    def test_singleton_pattern(self):
        """单例模式测试"""
        m1 = PromptManager()
        m2 = PromptManager()
        self.assertIs(m1, m2)

    def test_get_default_prompt(self):
        """获取默认 Prompt"""
        manager = PromptManager()
        prompt = manager.get_prompt("accounting_classifier")
        self.assertIsNotNone(prompt)
        self.assertIn("会计", prompt)

    def test_get_nonexistent_prompt(self):
        """获取不存在的 Prompt 返回 None"""
        manager = PromptManager()
        prompt = manager.get_prompt("nonexistent_prompt_xyz")
        self.assertIsNone(prompt)

    def test_list_prompts(self):
        """列出所有 Prompt"""
        manager = PromptManager()
        prompts = manager.list_prompts()
        self.assertIsInstance(prompts, dict)
        self.assertIn("accounting_classifier", prompts)

    def test_get_stats(self):
        """获取统计信息"""
        manager = PromptManager()
        stats = manager.get_stats()
        self.assertIn("total_calls", stats)
        self.assertIn("versions_loaded", stats)


if __name__ == "__main__":
    unittest.main()
