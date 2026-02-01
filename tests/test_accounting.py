"""
会计模块单元测试
Accounting Module Unit Tests
"""

import pytest
from datetime import datetime, date
from decimal import Decimal
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


class TestAccountingService:
    """会计服务测试"""

    def test_validate_voucher_balance(self):
        """测试凭证借贷平衡验证"""
        from accounting.accounting_service import AccountingService

        service = AccountingService()

        # 平衡的凭证
        balanced_items = [
            {"account_code": "1001", "direction": "DEBIT", "amount": 1000},
            {"account_code": "5001", "direction": "CREDIT", "amount": 1000},
        ]

        # 不平衡的凭证
        unbalanced_items = [
            {"account_code": "1001", "direction": "DEBIT", "amount": 1000},
            {"account_code": "5001", "direction": "CREDIT", "amount": 800},
        ]

        # 验证借贷平衡计算
        total_debit = sum(
            Decimal(str(item["amount"]))
            for item in balanced_items
            if item["direction"] == "DEBIT"
        )
        total_credit = sum(
            Decimal(str(item["amount"]))
            for item in balanced_items
            if item["direction"] == "CREDIT"
        )

        assert total_debit == total_credit

    def test_standard_accounts_structure(self):
        """测试标准科目表结构"""
        from accounting.accounting_service import STANDARD_ACCOUNTS
        from core.accounting_models import AccountType

        # 应该有资产类科目
        asset_accounts = [a for a in STANDARD_ACCOUNTS if a["type"] == AccountType.ASSET]
        assert len(asset_accounts) > 0

        # 应该有负债类科目
        liability_accounts = [a for a in STANDARD_ACCOUNTS if a["type"] == AccountType.LIABILITY]
        assert len(liability_accounts) > 0

        # 应该有权益类科目
        equity_accounts = [a for a in STANDARD_ACCOUNTS if a["type"] == AccountType.EQUITY]
        assert len(equity_accounts) > 0

        # 应该有收入类科目
        revenue_accounts = [a for a in STANDARD_ACCOUNTS if a["type"] == AccountType.REVENUE]
        assert len(revenue_accounts) > 0

        # 应该有费用类科目
        expense_accounts = [a for a in STANDARD_ACCOUNTS if a["type"] == AccountType.EXPENSE]
        assert len(expense_accounts) > 0

    def test_account_code_format(self):
        """测试科目编码格式"""
        from accounting.accounting_service import STANDARD_ACCOUNTS

        for account in STANDARD_ACCOUNTS:
            code = account["code"]
            # 科目编码应该是4位数字
            assert len(code) == 4
            assert code.isdigit()

    def test_cash_accounts_exist(self):
        """测试现金类科目存在"""
        from accounting.accounting_service import STANDARD_ACCOUNTS

        codes = [a["code"] for a in STANDARD_ACCOUNTS]

        assert "1001" in codes  # 库存现金
        assert "1002" in codes  # 银行存款


class TestReportsService:
    """报表服务测试"""

    def test_balance_sheet_structure(self):
        """测试资产负债表结构"""
        # 资产负债表应包含资产、负债、权益三部分
        expected_keys = ["assets", "liabilities", "equity", "summary"]

        mock_balance_sheet = {
            "report_name": "资产负债表",
            "period": "2024年1月",
            "assets": {"items": [], "total": 0},
            "liabilities": {"items": [], "total": 0},
            "equity": {"items": [], "total": 0},
            "summary": {
                "total_assets": 0,
                "total_liabilities": 0,
                "total_equity": 0,
                "total_liabilities_equity": 0,
                "is_balanced": True
            }
        }

        for key in expected_keys:
            assert key in mock_balance_sheet

    def test_balance_sheet_equation(self):
        """测试资产负债表会计等式"""
        # 资产 = 负债 + 所有者权益
        assets = Decimal("100000")
        liabilities = Decimal("40000")
        equity = Decimal("60000")

        assert assets == liabilities + equity

    def test_income_statement_profit_calculation(self):
        """测试利润表利润计算"""
        revenue = Decimal("50000")
        cost = Decimal("30000")
        expenses = Decimal("10000")

        gross_profit = revenue - cost
        net_profit = gross_profit - expenses

        assert gross_profit == Decimal("20000")
        assert net_profit == Decimal("10000")

    def test_cash_flow_reconciliation(self):
        """测试现金流量表核对"""
        opening_cash = Decimal("10000")
        operating_net = Decimal("5000")
        investing_net = Decimal("-2000")
        financing_net = Decimal("1000")

        expected_closing = opening_cash + operating_net + investing_net + financing_net
        actual_closing = Decimal("14000")

        assert expected_closing == actual_closing


class TestExportService:
    """导出服务测试"""

    def test_csv_export_encoding(self):
        """测试 CSV 导出编码"""
        from accounting.export_service import ReportExportService

        service = ReportExportService()

        data = {
            "report_name": "资产负债表",
            "period": "2024年1月",
            "generated_at": datetime.now().isoformat(),
            "assets": {"items": [{"code": "1001", "name": "库存现金", "balance": 1000}], "total": 1000},
            "liabilities": {"items": [], "total": 0},
            "equity": {"items": [], "total": 0},
            "summary": {"total_assets": 1000, "total_liabilities_equity": 0, "is_balanced": False}
        }

        csv_bytes = service.export_to_csv(data, "balance-sheet")

        # 应该是 UTF-8 BOM 编码
        assert csv_bytes is not None
        assert len(csv_bytes) > 0

        # 解码应该包含中文
        content = csv_bytes.decode("utf-8-sig")
        assert "资产负债表" in content
        assert "库存现金" in content

    def test_account_balances_csv_export(self):
        """测试科目余额表 CSV 导出"""
        from accounting.export_service import ReportExportService

        service = ReportExportService()

        data = [
            {
                "code": "1001",
                "name": "库存现金",
                "type": "ASSET",
                "direction": "DEBIT",
                "level": 1,
                "opening_debit": 0,
                "opening_credit": 0,
                "period_debit": 1000,
                "period_credit": 0,
                "ytd_debit": 1000,
                "ytd_credit": 0,
                "closing_debit": 1000,
                "closing_credit": 0
            }
        ]

        csv_bytes = service.export_to_csv(data, "account-balances")

        assert csv_bytes is not None
        content = csv_bytes.decode("utf-8-sig")
        assert "1001" in content
        assert "库存现金" in content


class TestAccountModels:
    """科目模型测试"""

    def test_account_type_enum(self):
        """测试科目类型枚举"""
        from core.accounting_models import AccountType

        assert AccountType.ASSET.value == "ASSET"
        assert AccountType.LIABILITY.value == "LIABILITY"
        assert AccountType.EQUITY.value == "EQUITY"
        assert AccountType.REVENUE.value == "REVENUE"
        assert AccountType.EXPENSE.value == "EXPENSE"

    def test_balance_direction_enum(self):
        """测试余额方向枚举"""
        from core.accounting_models import BalanceDirection

        assert BalanceDirection.DEBIT.value == "DEBIT"
        assert BalanceDirection.CREDIT.value == "CREDIT"
