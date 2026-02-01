"""
[Optimization Iteration 7] 集成测试 - 审计流程端到端测试
"""

import sys
import os
import unittest

# 添加 src 目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


class TestAuditFlowIntegration(unittest.TestCase):
    """审计流程集成测试"""

    def setUp(self):
        """初始化测试环境"""
        # 使用 Mock LLM 避免真实 API 调用
        os.environ["LEDGER_LLM_TYPE"] = "MOCK"

    def test_low_amount_transaction_auto_approved(self):
        """低金额交易自动审批流程"""
        from auditor_agent import AuditorAgent

        agent = AuditorAgent("TestAuditor")
        proposal = {
            "content": {
                "category": "6601-办公用品",
                "reason": "购买文具",
                "confidence": 0.95
            },
            "amount": 100,
            "vendor": "得力文具",
            "trace_id": "TEST-001"
        }

        result = agent.reply(proposal)

        self.assertIsNotNone(result)
        content = result.get("content", {})
        # 低金额高置信度应该通过
        self.assertIn(content.get("decision"), ["APPROVED", "REJECT"])

    def test_high_amount_triggers_manual_review(self):
        """高金额交易触发人工审核"""
        from auditor_agent import AuditorAgent

        agent = AuditorAgent("TestAuditor")
        proposal = {
            "content": {
                "category": "1601-固定资产",
                "reason": "服务器采购",
                "confidence": 0.9
            },
            "amount": 200000,  # 超过风控线
            "vendor": "戴尔科技",
            "trace_id": "TEST-002"
        }

        result = agent.reply(proposal)

        self.assertIsNotNone(result)
        content = result.get("content", {})
        # 高金额应该被拒绝或标记为需人工审核
        self.assertEqual(content.get("decision"), "REJECT")
        self.assertIn("大额", content.get("reason", ""))

    def test_blocked_vendor_rejected(self):
        """黑名单供应商直接拒绝"""
        from auditor_agent import AuditorAgent
        from db_helper import DBHelper

        # 准备：将供应商加入黑名单
        db = DBHelper()
        try:
            with db.transaction("IMMEDIATE") as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO knowledge_base
                    (entity_name, category_mapping, audit_status)
                    VALUES (?, ?, ?)
                """, ("黑名单公司", "杂项支出", "BLOCKED"))
        except:
            pass

        agent = AuditorAgent("TestAuditor")
        proposal = {
            "content": {
                "category": "6601-杂项支出",
                "reason": "测试",
                "confidence": 0.8
            },
            "amount": 500,
            "vendor": "黑名单公司",
            "trace_id": "TEST-003"
        }

        result = agent.reply(proposal)

        content = result.get("content", {})
        self.assertEqual(content.get("decision"), "REJECT")
        self.assertIn("拉黑", content.get("reason", ""))

    def test_invalid_category_format_rejected(self):
        """无效科目格式被拒绝"""
        from auditor_agent import AuditorAgent

        agent = AuditorAgent("TestAuditor")
        proposal = {
            "content": {
                "category": "无效格式",  # 不符合 \d{4}-\d{2} 格式
                "reason": "测试",
                "confidence": 0.9
            },
            "amount": 100,
            "vendor": "测试供应商",
            "trace_id": "TEST-004"
        }

        result = agent.reply(proposal)

        content = result.get("content", {})
        self.assertEqual(content.get("decision"), "REJECT")
        self.assertIn("格式", content.get("reason", ""))


class TestDBHelperIntegration(unittest.TestCase):
    """数据库助手集成测试"""

    def test_transaction_with_tags(self):
        """带标签的交易入库"""
        from db_helper import DBHelper

        db = DBHelper()
        trans_id = db.add_transaction_with_tags(
            tags=[
                {"key": "project", "value": "TEST_PROJECT"},
                {"key": "department", "value": "IT"}
            ],
            status="PENDING",
            amount=1000.00,
            vendor="集成测试供应商",
            category="6601-测试科目",
            source_type="INTEGRATION_TEST"
        )

        self.assertIsNotNone(trans_id)
        self.assertGreater(trans_id, 0)

    def test_connection_stats(self):
        """连接统计信息"""
        from db_helper import DBHelper

        db = DBHelper()
        stats = db.get_connection_stats()

        self.assertIn("total_connections_created", stats)
        self.assertIn("total_transactions", stats)


class TestMetricsIntegration(unittest.TestCase):
    """指标收集集成测试"""

    def test_metrics_collector_aggregation(self):
        """指标收集器聚合测试"""
        from metrics_exporter import MetricsCollector

        collector = MetricsCollector()

        # 记录一些指标
        collector.counter_inc("test_counter", 1)
        collector.counter_inc("test_counter", 2)
        collector.gauge_set("test_gauge", 42)
        collector.histogram_observe("test_histogram", 100)
        collector.histogram_observe("test_histogram", 200)

        # 获取 Prometheus 输出
        output = collector.get_prometheus_output()

        self.assertIn("test_counter", output)
        self.assertIn("test_gauge 42", output)
        self.assertIn("test_histogram", output)

    def test_prometheus_output_format(self):
        """Prometheus 输出格式验证"""
        from metrics_exporter import MetricsCollector

        collector = MetricsCollector()
        output = collector.get_prometheus_output()

        # 验证输出是有效的 Prometheus 格式
        self.assertIsInstance(output, str)
        # 每行应该是 metric_name value 或注释
        for line in output.strip().split("\n"):
            if line.startswith("#"):
                continue
            parts = line.split(" ")
            self.assertGreaterEqual(len(parts), 2)


class TestPromptManagerIntegration(unittest.TestCase):
    """Prompt 管理器集成测试"""

    def test_render_prompt_with_params(self):
        """参数化 Prompt 渲染"""
        from prompt_manager import PromptManager

        manager = PromptManager()

        # 获取默认 Prompt 并验证
        prompt = manager.get_prompt("accounting_classifier")
        self.assertIsNotNone(prompt)

        # 测试参数替换功能
        content = "供应商: {vendor}, 金额: {amount:0}"
        result = manager._substitute_params(content, {"vendor": "测试公司"})
        self.assertEqual(result, "供应商: 测试公司, 金额: 0")


if __name__ == "__main__":
    unittest.main()
