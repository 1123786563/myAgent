"""
财务报表服务
Financial Reports Service - Balance Sheet, Income Statement, Cash Flow Statement
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, date
from decimal import Decimal
from core.db_helper import DBHelper
from core.accounting_models import (
    Account, AccountType, BalanceDirection, AccountBalance, Voucher, VoucherItem
)
from infra.logger import get_logger

log = get_logger("ReportsService")


class FinancialReportsService:
    """财务报表服务"""

    def __init__(self):
        self.db = DBHelper()

    # ==================== 资产负债表 ====================

    def get_balance_sheet(
        self,
        organization_id: int,
        year: int,
        month: int
    ) -> Dict[str, Any]:
        """
        生成资产负债表

        资产 = 负债 + 所有者权益
        """
        with self.db.transaction() as session:
            # 获取所有科目余额
            balances = session.query(AccountBalance).join(Account).filter(
                AccountBalance.organization_id == organization_id,
                AccountBalance.year == year,
                AccountBalance.month == month
            ).all()

            # 按类型汇总
            assets = {"items": [], "total": Decimal('0')}
            liabilities = {"items": [], "total": Decimal('0')}
            equity = {"items": [], "total": Decimal('0')}

            for bal in balances:
                account = bal.account
                # 计算余额 (考虑借贷方向)
                if account.balance_direction == BalanceDirection.DEBIT:
                    balance = (bal.closing_debit or Decimal('0')) - (bal.closing_credit or Decimal('0'))
                else:
                    balance = (bal.closing_credit or Decimal('0')) - (bal.closing_debit or Decimal('0'))

                if balance == 0:
                    continue

                item = {
                    "code": account.code,
                    "name": account.name,
                    "balance": float(balance)
                }

                if account.account_type == AccountType.ASSET:
                    assets["items"].append(item)
                    assets["total"] += balance
                elif account.account_type == AccountType.LIABILITY:
                    liabilities["items"].append(item)
                    liabilities["total"] += balance
                elif account.account_type == AccountType.EQUITY:
                    equity["items"].append(item)
                    equity["total"] += balance

            # 验证平衡
            total_assets = assets["total"]
            total_liabilities_equity = liabilities["total"] + equity["total"]
            is_balanced = abs(total_assets - total_liabilities_equity) < Decimal('0.01')

            return {
                "report_name": "资产负债表",
                "period": f"{year}年{month}月",
                "generated_at": datetime.now().isoformat(),
                "assets": {
                    "items": sorted(assets["items"], key=lambda x: x["code"]),
                    "total": float(assets["total"])
                },
                "liabilities": {
                    "items": sorted(liabilities["items"], key=lambda x: x["code"]),
                    "total": float(liabilities["total"])
                },
                "equity": {
                    "items": sorted(equity["items"], key=lambda x: x["code"]),
                    "total": float(equity["total"])
                },
                "summary": {
                    "total_assets": float(total_assets),
                    "total_liabilities": float(liabilities["total"]),
                    "total_equity": float(equity["total"]),
                    "total_liabilities_equity": float(total_liabilities_equity),
                    "is_balanced": is_balanced
                }
            }

    # ==================== 利润表 ====================

    def get_income_statement(
        self,
        organization_id: int,
        year: int,
        month: int,
        is_ytd: bool = False
    ) -> Dict[str, Any]:
        """
        生成利润表

        净利润 = 收入 - 成本 - 费用
        """
        with self.db.transaction() as session:
            balances = session.query(AccountBalance).join(Account).filter(
                AccountBalance.organization_id == organization_id,
                AccountBalance.year == year,
                AccountBalance.month == month
            ).all()

            # 收入类
            revenue = {"items": [], "total": Decimal('0')}
            # 成本类
            cost = {"items": [], "total": Decimal('0')}
            # 费用类
            expenses = {"items": [], "total": Decimal('0')}

            for bal in balances:
                account = bal.account

                # 使用本期发生额或年累计
                if is_ytd:
                    debit = bal.ytd_debit or Decimal('0')
                    credit = bal.ytd_credit or Decimal('0')
                else:
                    debit = bal.period_debit or Decimal('0')
                    credit = bal.period_credit or Decimal('0')

                if account.account_type == AccountType.REVENUE:
                    # 收入类: 贷方发生额
                    amount = credit - debit
                    if amount != 0:
                        revenue["items"].append({
                            "code": account.code,
                            "name": account.name,
                            "amount": float(amount)
                        })
                        revenue["total"] += amount

                elif account.account_type == AccountType.EXPENSE:
                    # 费用类: 借方发生额
                    amount = debit - credit
                    if amount != 0:
                        # 区分成本和费用
                        if account.code.startswith("54") or account.code.startswith("40"):
                            cost["items"].append({
                                "code": account.code,
                                "name": account.name,
                                "amount": float(amount)
                            })
                            cost["total"] += amount
                        else:
                            expenses["items"].append({
                                "code": account.code,
                                "name": account.name,
                                "amount": float(amount)
                            })
                            expenses["total"] += amount

            # 计算各级利润
            gross_profit = revenue["total"] - cost["total"]  # 毛利润
            operating_profit = gross_profit - expenses["total"]  # 营业利润
            # 简化处理，暂不计算营业外收支
            net_profit = operating_profit

            return {
                "report_name": "利润表",
                "period": f"{year}年{month}月" + (" (年累计)" if is_ytd else ""),
                "generated_at": datetime.now().isoformat(),
                "revenue": {
                    "items": sorted(revenue["items"], key=lambda x: x["code"]),
                    "total": float(revenue["total"])
                },
                "cost": {
                    "items": sorted(cost["items"], key=lambda x: x["code"]),
                    "total": float(cost["total"])
                },
                "expenses": {
                    "items": sorted(expenses["items"], key=lambda x: x["code"]),
                    "total": float(expenses["total"])
                },
                "summary": {
                    "total_revenue": float(revenue["total"]),
                    "total_cost": float(cost["total"]),
                    "gross_profit": float(gross_profit),
                    "total_expenses": float(expenses["total"]),
                    "operating_profit": float(operating_profit),
                    "net_profit": float(net_profit),
                    "profit_margin": float(net_profit / revenue["total"] * 100) if revenue["total"] else 0
                }
            }

    # ==================== 现金流量表 ====================

    def get_cash_flow_statement(
        self,
        organization_id: int,
        year: int,
        month: int
    ) -> Dict[str, Any]:
        """
        生成现金流量表 (简易版 - 直接法)

        现金流量 = 经营活动 + 投资活动 + 筹资活动
        """
        with self.db.transaction() as session:
            # 获取现金类科目的发生额
            cash_accounts = session.query(Account).filter(
                Account.organization_id == organization_id,
                Account.code.in_(["1001", "1002", "1012"])  # 库存现金、银行存款、其他货币资金
            ).all()

            cash_account_ids = [a.id for a in cash_accounts]

            # 查询本期现金相关的凭证分录
            voucher_items = session.query(VoucherItem).join(Voucher).filter(
                Voucher.organization_id == organization_id,
                Voucher.year == year,
                Voucher.month == month,
                Voucher.status == "POSTED",
                VoucherItem.account_id.in_(cash_account_ids)
            ).all()

            # 简化分类：根据对方科目判断现金流类型
            operating = {"inflow": Decimal('0'), "outflow": Decimal('0'), "items": []}
            investing = {"inflow": Decimal('0'), "outflow": Decimal('0'), "items": []}
            financing = {"inflow": Decimal('0'), "outflow": Decimal('0'), "items": []}

            for item in voucher_items:
                amount = item.amount
                is_inflow = item.direction == BalanceDirection.DEBIT

                # 获取对方科目来判断类型
                voucher = item.voucher
                other_items = [i for i in voucher.items if i.id != item.id]

                category = operating  # 默认为经营活动

                for other in other_items:
                    other_account = other.account
                    code = other_account.code

                    # 投资活动：固定资产、无形资产、长期投资等
                    if code.startswith("16") or code.startswith("17") or code.startswith("11"):
                        category = investing
                        break
                    # 筹资活动：借款、实收资本等
                    elif code.startswith("20") or code.startswith("25") or code.startswith("30"):
                        category = financing
                        break

                if is_inflow:
                    category["inflow"] += amount
                else:
                    category["outflow"] += amount

                category["items"].append({
                    "voucher_id": item.voucher_id,
                    "amount": float(amount),
                    "direction": "inflow" if is_inflow else "outflow",
                    "summary": item.summary or voucher.summary
                })

            # 计算净现金流
            operating_net = operating["inflow"] - operating["outflow"]
            investing_net = investing["inflow"] - investing["outflow"]
            financing_net = financing["inflow"] - financing["outflow"]
            total_net = operating_net + investing_net + financing_net

            # 获取期初期末现金余额
            opening_cash = Decimal('0')
            closing_cash = Decimal('0')

            for acc_id in cash_account_ids:
                bal = session.query(AccountBalance).filter_by(
                    organization_id=organization_id,
                    account_id=acc_id,
                    year=year,
                    month=month
                ).first()
                if bal:
                    opening_cash += (bal.opening_debit or Decimal('0')) - (bal.opening_credit or Decimal('0'))
                    closing_cash += (bal.closing_debit or Decimal('0')) - (bal.closing_credit or Decimal('0'))

            return {
                "report_name": "现金流量表",
                "period": f"{year}年{month}月",
                "generated_at": datetime.now().isoformat(),
                "operating_activities": {
                    "inflow": float(operating["inflow"]),
                    "outflow": float(operating["outflow"]),
                    "net": float(operating_net)
                },
                "investing_activities": {
                    "inflow": float(investing["inflow"]),
                    "outflow": float(investing["outflow"]),
                    "net": float(investing_net)
                },
                "financing_activities": {
                    "inflow": float(financing["inflow"]),
                    "outflow": float(financing["outflow"]),
                    "net": float(financing_net)
                },
                "summary": {
                    "net_cash_flow": float(total_net),
                    "opening_cash": float(opening_cash),
                    "closing_cash": float(closing_cash),
                    "cash_change": float(closing_cash - opening_cash),
                    "is_reconciled": abs((closing_cash - opening_cash) - total_net) < Decimal('0.01')
                }
            }

    # ==================== 科目余额表 ====================

    def get_account_balance_report(
        self,
        organization_id: int,
        year: int,
        month: int,
        account_type: Optional[str] = None,
        level: Optional[int] = None
    ) -> List[Dict]:
        """获取科目余额表"""
        with self.db.transaction() as session:
            query = session.query(AccountBalance).join(Account).filter(
                AccountBalance.organization_id == organization_id,
                AccountBalance.year == year,
                AccountBalance.month == month
            )

            if account_type:
                query = query.filter(Account.account_type == AccountType(account_type))
            if level:
                query = query.filter(Account.level <= level)

            balances = query.all()

            result = []
            for bal in balances:
                account = bal.account
                result.append({
                    "code": account.code,
                    "name": account.name,
                    "type": account.account_type.value,
                    "direction": account.balance_direction.value,
                    "level": account.level,
                    "opening_debit": float(bal.opening_debit or 0),
                    "opening_credit": float(bal.opening_credit or 0),
                    "period_debit": float(bal.period_debit or 0),
                    "period_credit": float(bal.period_credit or 0),
                    "ytd_debit": float(bal.ytd_debit or 0),
                    "ytd_credit": float(bal.ytd_credit or 0),
                    "closing_debit": float(bal.closing_debit or 0),
                    "closing_credit": float(bal.closing_credit or 0)
                })

            return sorted(result, key=lambda x: x["code"])

    # ==================== 明细账 ====================

    def get_account_ledger(
        self,
        organization_id: int,
        account_code: str,
        year: int,
        month: Optional[int] = None
    ) -> Dict[str, Any]:
        """获取科目明细账"""
        with self.db.transaction() as session:
            account = session.query(Account).filter_by(
                organization_id=organization_id,
                code=account_code
            ).first()

            if not account:
                return {"error": "科目不存在"}

            query = session.query(VoucherItem).join(Voucher).filter(
                Voucher.organization_id == organization_id,
                Voucher.year == year,
                Voucher.status == "POSTED",
                VoucherItem.account_id == account.id
            )

            if month:
                query = query.filter(Voucher.month == month)

            items = query.order_by(Voucher.voucher_date, Voucher.voucher_number).all()

            # 计算余额
            running_balance = Decimal('0')
            entries = []

            for item in items:
                voucher = item.voucher
                if item.direction == BalanceDirection.DEBIT:
                    running_balance += item.amount
                    debit = float(item.amount)
                    credit = 0
                else:
                    running_balance -= item.amount
                    debit = 0
                    credit = float(item.amount)

                entries.append({
                    "date": voucher.voucher_date.strftime("%Y-%m-%d"),
                    "voucher_type": voucher.voucher_type,
                    "voucher_number": voucher.voucher_number,
                    "summary": item.summary or voucher.summary,
                    "debit": debit,
                    "credit": credit,
                    "balance": float(running_balance),
                    "direction": "借" if running_balance >= 0 else "贷"
                })

            return {
                "account_code": account.code,
                "account_name": account.name,
                "period": f"{year}年" + (f"{month}月" if month else ""),
                "entries": entries,
                "summary": {
                    "total_debit": sum(e["debit"] for e in entries),
                    "total_credit": sum(e["credit"] for e in entries),
                    "closing_balance": float(running_balance)
                }
            }


# 单例
_reports_service = None


def get_reports_service() -> FinancialReportsService:
    """获取报表服务单例"""
    global _reports_service
    if _reports_service is None:
        _reports_service = FinancialReportsService()
    return _reports_service
