import unittest
import sys
import os
import re
import threading
import time
import uuid
from unittest.mock import MagicMock, patch
from pathlib import Path

# --- MOCK AGENTSCOPE BEGIN ---
mock_as = MagicMock()
mock_as.agents = MagicMock()
mock_as.message = MagicMock()

class MockAgentBase:
    def __init__(self, name):
        self.name = name
    def reply(self, x):
        pass

class MockMsg(dict):
    def __init__(self, **kwargs):
        super().__init__(kwargs)
        for k, v in kwargs.items():
            setattr(self, k, v)

mock_as.agents.AgentBase = MockAgentBase
mock_as.message.Msg = MockMsg
sys.modules["agentscope"] = mock_as
sys.modules["agentscope.agent"] = mock_as.agents
sys.modules["agentscope.message"] = mock_as.message
# --- MOCK AGENTSCOPE END ---

# 确保能加载 src 模块
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from privacy_guard import PrivacyGuard
from config_manager import ConfigManager
from accounting_agent import AccountingAgent, RecoveryWorker
from match_engine import MatchEngine
from db_helper import DBHelper
from sentinel_agent import SentinelAgent
from collector import CollectorWorker
import queue

class TestLedgerAlpha(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 优化点：测试环境感知，使用临时测试数据库
        db_path = "/tmp/test_ledger_alpha.db"
        if os.path.exists(db_path):
            os.remove(db_path)
        os.environ["LEDGER_PATH_DB"] = db_path
        ConfigManager.load(force=True)

    def setUp(self):
        # 每次测试前清理数据库，确保环境纯净
        self.db = DBHelper()
        # Ensure clean state
        try: self.db._get_conn().rollback()
        except: pass
        
        with self.db.transaction("IMMEDIATE") as conn:
            conn.execute("DELETE FROM transactions")
            conn.execute("DELETE FROM pending_entries")
            conn.execute("DELETE FROM dept_budgets")
            conn.execute("DELETE FROM system_events")
        self.guard = PrivacyGuard()

    def tearDown(self):
        pass

    def test_privacy_roles(self):
        """测试不同角色的脱敏表现"""
        raw = "手机13812345678"
        admin_guard = PrivacyGuard(role="ADMIN")
        auditor_guard = PrivacyGuard(role="AUDITOR")
        guest_guard = PrivacyGuard(role="GUEST")
        
        self.assertEqual(admin_guard.desensitize(raw), raw)
        self.assertTrue(re.search(r'138\*{4}5678', auditor_guard.desensitize(raw)))
        self.assertEqual(guest_guard.desensitize(raw), "手机[PHONE_SECRET]")

    def test_db_concurrency_stress(self):
        """测试数据库在高并发写入下的稳定性"""
        errors = []
        def concurrent_writer(thread_id):
            try:
                db = DBHelper()
                for i in range(20):
                    db.add_transaction(amount=10.0, vendor=f"T{thread_id}", status="PENDING")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=concurrent_writer, args=(i,)) for i in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()
        
        self.assertEqual(len(errors), 0, f"并发写入出现错误: {errors}")

    def test_sentinel_compliance(self):
        """测试 Sentinel 的合规性检查 (Budget & Relevance)"""
        sentinel = SentinelAgent("TestSentinel")
        
        # 1. 业务相关性测试
        proposal_bad = {"vendor": "肯德基餐饮", "category": "办公用品", "amount": 50}
        passed, reason = sentinel.check_transaction_compliance(proposal_bad)
        self.assertFalse(passed)
        self.assertIn("业务相关性存疑", reason)

        # 2. 预算熔断测试
        with self.db.transaction("IMMEDIATE") as conn:
            conn.execute("INSERT INTO dept_budgets (dept_name, monthly_limit, current_spent) VALUES ('R&D', 1000, 900)")
        
        proposal_over = {
            "vendor": "AWS", 
            "category": "技术服务", 
            "amount": 200, 
            "tags": [{"key": "department", "value": "R&D"}]
        }
        passed, reason = sentinel.check_transaction_compliance(proposal_over)
        self.assertFalse(passed)
        self.assertIn("预算熔断", reason)

    def test_accounting_recovery(self):
        """测试 AccountingAgent 的自愈恢复逻辑"""
        agent = AccountingAgent("TestAccountant")
        worker = RecoveryWorker(agent)
        
        # 1. 插入一个被驳回的单据
        tid = self.db.add_transaction(
            vendor="阿里云计算", 
            amount=500.0, 
            status="REJECTED", 
            category="错误科目",
            inference_log="{}"
        )
        
        # 2. 执行恢复
        worker._attempt_recovery({"id": tid, "vendor": "阿里云计算", "amount": 500.0, "inference_log": "{}"})
        
        # 3. 验证结果
        with self.db.transaction("DEFERRED") as conn:
            row = conn.execute("SELECT status, category FROM transactions WHERE id = ?", (tid,)).fetchone()
            self.assertEqual(row['status'], 'PENDING_AUDIT')
            self.assertEqual(row['category'], '技术服务费-云资源')

    def test_collector_traceability(self):
        """测试采集器是否正确生成 Trace ID"""
        q = queue.Queue()
        collector = CollectorWorker(q, 0)
        
        # 模拟文件处理
        test_file = "/tmp/test_receipt.jpg"
        with open(test_file, 'w') as f: f.write("dummy content" * 20)
        
        try:
            collector._process_file(test_file)
            
            # 验证 DB 中是否有 trace_id
            with self.db.transaction("DEFERRED") as conn:
                row = conn.execute("SELECT trace_id FROM transactions WHERE file_path = ?", (test_file,)).fetchone()
                self.assertIsNotNone(row)
                self.assertTrue(len(row['trace_id']) > 10)
        finally:
            if os.path.exists(test_file): os.remove(test_file)

    def test_end_to_end_matching_flow(self):
        """集成测试：模拟完整对账链路"""
        self.db.add_transaction(amount=99.9, vendor='模拟供应商', status='PENDING')
        with self.db.transaction("IMMEDIATE") as conn:
            conn.execute("INSERT INTO pending_entries (amount, vendor_keyword, status) VALUES (99.9, '模拟', 'PENDING')")
        
        engine = MatchEngine()
        engine.run_matching()
        
        with self.db.transaction("DEFERRED") as conn:
            res = conn.execute("SELECT status FROM transactions WHERE amount = 99.9").fetchone()
            self.assertEqual(res['status'], 'MATCHED')

if __name__ == "__main__":
    unittest.main()
