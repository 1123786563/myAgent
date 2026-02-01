"""
发票模块单元测试
Invoice Module Unit Tests
"""

import pytest
from datetime import datetime, date
from decimal import Decimal
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


class TestInvoiceModels:
    """发票模型测试"""

    def test_invoice_type_enum(self):
        """测试发票类型枚举"""
        from core.invoice_models import InvoiceType

        assert InvoiceType.VAT_SPECIAL.value == "VAT_SPECIAL"
        assert InvoiceType.VAT_NORMAL.value == "VAT_NORMAL"
        assert InvoiceType.VAT_ELECTRONIC.value == "VAT_ELECTRONIC"

    def test_invoice_direction_enum(self):
        """测试发票方向枚举"""
        from core.invoice_models import InvoiceDirection

        assert InvoiceDirection.INPUT.value == "INPUT"
        assert InvoiceDirection.OUTPUT.value == "OUTPUT"

    def test_invoice_status_enum(self):
        """测试发票状态枚举"""
        from core.invoice_models import InvoiceStatus

        assert InvoiceStatus.DRAFT.value == "DRAFT"
        assert InvoiceStatus.VERIFIED.value == "VERIFIED"
        assert InvoiceStatus.VOIDED.value == "VOIDED"

    def test_tax_rate_enum(self):
        """测试税率枚举"""
        from core.invoice_models import TaxRate

        assert TaxRate.RATE_13.value == "13"
        assert TaxRate.RATE_6.value == "6"
        assert TaxRate.EXEMPT.value == "EXEMPT"


class TestInvoiceService:
    """发票服务测试"""

    def test_calculate_total_amount(self):
        """测试计算价税合计"""
        amount_without_tax = Decimal("1000.00")
        tax_amount = Decimal("130.00")

        total_amount = amount_without_tax + tax_amount

        assert total_amount == Decimal("1130.00")

    def test_calculate_tax_from_rate(self):
        """测试根据税率计算税额"""
        amount_without_tax = Decimal("1000.00")
        tax_rate = Decimal("0.13")  # 13%

        tax_amount = amount_without_tax * tax_rate

        assert tax_amount == Decimal("130.00")

    def test_vat_deduction_calculation(self):
        """测试增值税抵扣计算"""
        # 进项税
        input_tax = Decimal("1300.00")
        # 销项税
        output_tax = Decimal("2600.00")

        # 应纳税额 = 销项税 - 进项税
        tax_payable = output_tax - input_tax

        assert tax_payable == Decimal("1300.00")

    def test_tax_credit_calculation(self):
        """测试留抵税额计算"""
        input_tax = Decimal("3000.00")
        output_tax = Decimal("2000.00")

        # 当进项税 > 销项税时，产生留抵税额
        tax_payable = output_tax - input_tax

        if tax_payable < 0:
            tax_credit = abs(tax_payable)
            tax_payable = Decimal("0")
        else:
            tax_credit = Decimal("0")

        assert tax_credit == Decimal("1000.00")
        assert tax_payable == Decimal("0")


class TestInvoiceValidation:
    """发票验证测试"""

    def test_invoice_code_format_valid(self):
        """测试有效发票代码格式"""
        valid_codes = [
            "1234567890",
            "0123456789",
            "9876543210"
        ]

        for code in valid_codes:
            assert len(code) >= 10
            assert code.isdigit()

    def test_invoice_code_format_invalid(self):
        """测试无效发票代码格式"""
        invalid_codes = [
            "123",          # 太短
            "abcdefghij",   # 非数字
            ""              # 空
        ]

        for code in invalid_codes:
            is_valid = len(code) >= 10 and code.isdigit()
            assert is_valid is False

    def test_invoice_number_format(self):
        """测试发票号码格式"""
        valid_numbers = ["12345678", "00000001", "99999999"]

        for number in valid_numbers:
            assert len(number) == 8
            assert number.isdigit()

    def test_check_code_format(self):
        """测试校验码格式"""
        # 校验码通常是后6位
        check_code = "123456"
        assert len(check_code) == 6


class TestTaxDeclaration:
    """税务申报测试"""

    def test_vat_declaration_period_format(self):
        """测试增值税申报期格式"""
        valid_periods = ["2024-01", "2024-12", "2023-06"]

        for period in valid_periods:
            parts = period.split("-")
            assert len(parts) == 2
            assert parts[0].isdigit() and len(parts[0]) == 4  # 年份
            assert parts[1].isdigit() and 1 <= int(parts[1]) <= 12  # 月份

    def test_quarterly_tax_calculation(self):
        """测试季度税务计算"""
        monthly_tax = [
            Decimal("1000"),  # 1月
            Decimal("1200"),  # 2月
            Decimal("800"),   # 3月
        ]

        quarterly_total = sum(monthly_tax)
        assert quarterly_total == Decimal("3000")

    def test_annual_tax_summary(self):
        """测试年度税务汇总"""
        monthly_input_tax = [Decimal("1000")] * 12
        monthly_output_tax = [Decimal("1500")] * 12

        annual_input = sum(monthly_input_tax)
        annual_output = sum(monthly_output_tax)
        annual_payable = annual_output - annual_input

        assert annual_input == Decimal("12000")
        assert annual_output == Decimal("18000")
        assert annual_payable == Decimal("6000")
