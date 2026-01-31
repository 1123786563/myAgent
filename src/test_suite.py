import unittest
import sys
import os
import re
import threading
import time
from unittest.mock import MagicMock, patch
from pathlib import Path

# 确保能加载 src 模块
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from privacy_guard import PrivacyGuard
from config_manager import ConfigManager
from accounting_agent import AccountingAgent
from match_engine import MatchEngine
from db_helper import DBHelper

class TestLedgerAlpha(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 优化点：测试环境感知，使用临时测试数据库
        os.environ["LEDGER_PATH_DB"] = "/tmp/test_ledger_alpha.db"
        ConfigManager.load(force=True)

    def setUp(self):
        # 每次测试前清理数据库，确保环境纯净
        self.db = DBHelper()
        with self.db.transaction("IMMEDIATE") as conn:
            conn.execute("DELETE FROM transactions")
            conn.execute("DELETE FROM pending_entries")
        self.guard = PrivacyGuard()

    def tearDown(self):
        # 可以在这里做清理工作
        pass

    def test_privacy_roles(self):
        """测试不同角色的脱敏表现"""
        raw = "手机13812345678"
        admin_guard = PrivacyGuard(role="ADMIN")
        auditor_guard = PrivacyGuard(role="AUDITOR")
        guest_guard = PrivacyGuard(role="GUEST")
        
        self.assertEqual(admin_guard.desensitize(raw), raw)
        # 审计员半脱敏
        self.assertTrue(re.search(r'138\*{4}5678', auditor_guard.desensitize(raw)))
        # 访客全脱敏
        self.assertEqual(guest_guard.desensitize(raw), "[PHONE_SECRET]")

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

    def test_accounting_agent_with_mock(self):
        """使用 Mock 替代真实 LLM 调用测试业务逻辑"""
        agent = AccountingAgent("MockPuppy")
        # 模拟规则库返回
        mock_reply = MagicMock()
        mock_reply.content = {"category": "交通费", "confidence": 0.99}
        
        with patch.object(AccountingAgent, 'reply', return_value=mock_reply):
            res = agent.reply({"content": "测试滴滴", "amount": 10})
            self.assertEqual(res.content["category"], "交通费")

    def test_end_to_end_matching_flow(self):
        """集成测试：模拟完整对账链路"""
        # 1. 注入模拟数据
        self.db.add_transaction(amount=99.9, vendor='模拟供应商', status='PENDING')
        with self.db.transaction("IMMEDIATE") as conn:
            conn.execute("INSERT INTO pending_entries (amount, vendor_keyword, status) VALUES (99.9, '模拟', 'PENDING')")
        
        # 2. 执行对账
        engine = MatchEngine()
        engine.run_matching()
        
        # 3. 校验结果
        with self.db.transaction("DEFERRED") as conn:
            res = conn.execute("SELECT status FROM transactions WHERE amount = 99.9").fetchone()
            self.assertEqual(res['status'], 'MATCHED')

if __name__ == "__main__":
    unittest.main()
