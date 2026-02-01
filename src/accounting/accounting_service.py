"""
会计科目服务
Accounting Service - Chart of Accounts, Vouchers, Balances
"""

from typing import Optional, List, Dict, Tuple, Any
from datetime import datetime, date
from decimal import Decimal
from core.db_helper import DBHelper
from core.accounting_models import (
    Account, AccountType, BalanceDirection, AccountCategory,
    AccountingPeriod, Voucher, VoucherItem, AccountBalance
)
from auth.services.audit_service import AuditService
from infra.logger import get_logger

log = get_logger("AccountingService")


# 标准科目表 (中国企业会计准则)
STANDARD_ACCOUNTS = [
    # 资产类 (1xxx)
    {"code": "1001", "name": "库存现金", "type": AccountType.ASSET, "category": AccountCategory.CASH, "direction": BalanceDirection.DEBIT},
    {"code": "1002", "name": "银行存款", "type": AccountType.ASSET, "category": AccountCategory.BANK, "direction": BalanceDirection.DEBIT},
    {"code": "1012", "name": "其他货币资金", "type": AccountType.ASSET, "category": AccountCategory.BANK, "direction": BalanceDirection.DEBIT},
    {"code": "1101", "name": "交易性金融资产", "type": AccountType.ASSET, "category": AccountCategory.OTHER_ASSET, "direction": BalanceDirection.DEBIT},
    {"code": "1121", "name": "应收票据", "type": AccountType.ASSET, "category": AccountCategory.RECEIVABLE, "direction": BalanceDirection.DEBIT},
    {"code": "1122", "name": "应收账款", "type": AccountType.ASSET, "category": AccountCategory.RECEIVABLE, "direction": BalanceDirection.DEBIT},
    {"code": "1123", "name": "预付账款", "type": AccountType.ASSET, "category": AccountCategory.PREPAID, "direction": BalanceDirection.DEBIT},
    {"code": "1131", "name": "应收股利", "type": AccountType.ASSET, "category": AccountCategory.RECEIVABLE, "direction": BalanceDirection.DEBIT},
    {"code": "1132", "name": "应收利息", "type": AccountType.ASSET, "category": AccountCategory.RECEIVABLE, "direction": BalanceDirection.DEBIT},
    {"code": "1221", "name": "其他应收款", "type": AccountType.ASSET, "category": AccountCategory.RECEIVABLE, "direction": BalanceDirection.DEBIT},
    {"code": "1231", "name": "坏账准备", "type": AccountType.ASSET, "category": AccountCategory.RECEIVABLE, "direction": BalanceDirection.CREDIT},
    {"code": "1401", "name": "材料采购", "type": AccountType.ASSET, "category": AccountCategory.INVENTORY, "direction": BalanceDirection.DEBIT},
    {"code": "1402", "name": "在途物资", "type": AccountType.ASSET, "category": AccountCategory.INVENTORY, "direction": BalanceDirection.DEBIT},
    {"code": "1403", "name": "原材料", "type": AccountType.ASSET, "category": AccountCategory.INVENTORY, "direction": BalanceDirection.DEBIT},
    {"code": "1405", "name": "库存商品", "type": AccountType.ASSET, "category": AccountCategory.INVENTORY, "direction": BalanceDirection.DEBIT},
    {"code": "1601", "name": "固定资产", "type": AccountType.ASSET, "category": AccountCategory.FIXED_ASSET, "direction": BalanceDirection.DEBIT},
    {"code": "1602", "name": "累计折旧", "type": AccountType.ASSET, "category": AccountCategory.FIXED_ASSET, "direction": BalanceDirection.CREDIT},
    {"code": "1701", "name": "无形资产", "type": AccountType.ASSET, "category": AccountCategory.INTANGIBLE, "direction": BalanceDirection.DEBIT},
    {"code": "1702", "name": "累计摊销", "type": AccountType.ASSET, "category": AccountCategory.INTANGIBLE, "direction": BalanceDirection.CREDIT},
    {"code": "1801", "name": "长期待摊费用", "type": AccountType.ASSET, "category": AccountCategory.OTHER_ASSET, "direction": BalanceDirection.DEBIT},

    # 负债类 (2xxx)
    {"code": "2001", "name": "短期借款", "type": AccountType.LIABILITY, "category": AccountCategory.OTHER_LIABILITY, "direction": BalanceDirection.CREDIT},
    {"code": "2201", "name": "应付票据", "type": AccountType.LIABILITY, "category": AccountCategory.PAYABLE, "direction": BalanceDirection.CREDIT},
    {"code": "2202", "name": "应付账款", "type": AccountType.LIABILITY, "category": AccountCategory.PAYABLE, "direction": BalanceDirection.CREDIT},
    {"code": "2203", "name": "预收账款", "type": AccountType.LIABILITY, "category": AccountCategory.ADVANCE, "direction": BalanceDirection.CREDIT},
    {"code": "2211", "name": "应付职工薪酬", "type": AccountType.LIABILITY, "category": AccountCategory.SALARY_PAYABLE, "direction": BalanceDirection.CREDIT},
    {"code": "2221", "name": "应交税费", "type": AccountType.LIABILITY, "category": AccountCategory.TAX_PAYABLE, "direction": BalanceDirection.CREDIT},
    {"code": "2231", "name": "应付利息", "type": AccountType.LIABILITY, "category": AccountCategory.PAYABLE, "direction": BalanceDirection.CREDIT},
    {"code": "2232", "name": "应付股利", "type": AccountType.LIABILITY, "category": AccountCategory.PAYABLE, "direction": BalanceDirection.CREDIT},
    {"code": "2241", "name": "其他应付款", "type": AccountType.LIABILITY, "category": AccountCategory.OTHER_LIABILITY, "direction": BalanceDirection.CREDIT},
    {"code": "2501", "name": "长期借款", "type": AccountType.LIABILITY, "category": AccountCategory.OTHER_LIABILITY, "direction": BalanceDirection.CREDIT},

    # 权益类 (3xxx)
    {"code": "3001", "name": "实收资本", "type": AccountType.EQUITY, "category": AccountCategory.CAPITAL, "direction": BalanceDirection.CREDIT},
    {"code": "3002", "name": "资本公积", "type": AccountType.EQUITY, "category": AccountCategory.RESERVE, "direction": BalanceDirection.CREDIT},
    {"code": "3101", "name": "盈余公积", "type": AccountType.EQUITY, "category": AccountCategory.RESERVE, "direction": BalanceDirection.CREDIT},
    {"code": "3103", "name": "本年利润", "type": AccountType.EQUITY, "category": AccountCategory.RETAINED_EARNINGS, "direction": BalanceDirection.CREDIT},
    {"code": "3104", "name": "利润分配", "type": AccountType.EQUITY, "category": AccountCategory.RETAINED_EARNINGS, "direction": BalanceDirection.CREDIT},

    # 成本类 (4xxx)
    {"code": "4001", "name": "生产成本", "type": AccountType.EXPENSE, "category": AccountCategory.MAIN_COST, "direction": BalanceDirection.DEBIT},
    {"code": "4101", "name": "制造费用", "type": AccountType.EXPENSE, "category": AccountCategory.MAIN_COST, "direction": BalanceDirection.DEBIT},

    # 损益类 - 收入 (5xxx)
    {"code": "5001", "name": "主营业务收入", "type": AccountType.REVENUE, "category": AccountCategory.MAIN_REVENUE, "direction": BalanceDirection.CREDIT},
    {"code": "5051", "name": "其他业务收入", "type": AccountType.REVENUE, "category": AccountCategory.OTHER_REVENUE, "direction": BalanceDirection.CREDIT},
    {"code": "5111", "name": "投资收益", "type": AccountType.REVENUE, "category": AccountCategory.OTHER_REVENUE, "direction": BalanceDirection.CREDIT},
    {"code": "5301", "name": "营业外收入", "type": AccountType.REVENUE, "category": AccountCategory.NON_OPERATING_INCOME, "direction": BalanceDirection.CREDIT},

    # 损益类 - 费用 (6xxx)
    {"code": "5401", "name": "主营业务成本", "type": AccountType.EXPENSE, "category": AccountCategory.MAIN_COST, "direction": BalanceDirection.DEBIT},
    {"code": "5402", "name": "其他业务成本", "type": AccountType.EXPENSE, "category": AccountCategory.MAIN_COST, "direction": BalanceDirection.DEBIT},
    {"code": "5403", "name": "税金及附加", "type": AccountType.EXPENSE, "category": AccountCategory.TAX_EXPENSE, "direction": BalanceDirection.DEBIT},
    {"code": "5601", "name": "销售费用", "type": AccountType.EXPENSE, "category": AccountCategory.OPERATING_EXPENSE, "direction": BalanceDirection.DEBIT},
    {"code": "5602", "name": "管理费用", "type": AccountType.EXPENSE, "category": AccountCategory.ADMIN_EXPENSE, "direction": BalanceDirection.DEBIT},
    {"code": "5603", "name": "财务费用", "type": AccountType.EXPENSE, "category": AccountCategory.FINANCE_EXPENSE, "direction": BalanceDirection.DEBIT},
    {"code": "5604", "name": "研发费用", "type": AccountType.EXPENSE, "category": AccountCategory.RD_EXPENSE, "direction": BalanceDirection.DEBIT},
    {"code": "5711", "name": "营业外支出", "type": AccountType.EXPENSE, "category": AccountCategory.NON_OPERATING_EXPENSE, "direction": BalanceDirection.DEBIT},
    {"code": "5801", "name": "所得税费用", "type": AccountType.EXPENSE, "category": AccountCategory.TAX_EXPENSE, "direction": BalanceDirection.DEBIT},
]


class AccountingService:
    """会计科目与凭证服务"""

    def __init__(self):
        self.db = DBHelper()

    # ==================== 科目管理 ====================

    def init_standard_accounts(self, organization_id: int, user_id: int) -> int:
        """初始化标准科目表"""
        count = 0
        with self.db.transaction() as session:
            for acc_data in STANDARD_ACCOUNTS:
                existing = session.query(Account).filter_by(
                    organization_id=organization_id,
                    code=acc_data["code"]
                ).first()
                if existing:
                    continue

                account = Account(
                    organization_id=organization_id,
                    code=acc_data["code"],
                    name=acc_data["name"],
                    full_name=acc_data["name"],
                    account_type=acc_data["type"],
                    category=acc_data.get("category"),
                    balance_direction=acc_data["direction"],
                    level=1,
                    is_leaf=True,
                    is_system=True,
                    is_active=True
                )
                session.add(account)
                count += 1

            AuditService.log(
                action="accounts.init_standard",
                user_id=user_id,
                organization_id=organization_id,
                new_values={"count": count}
            )

        log.info(f"Initialized {count} standard accounts for org {organization_id}")
        return count

    def create_account(
        self,
        organization_id: int,
        code: str,
        name: str,
        account_type: AccountType,
        balance_direction: BalanceDirection,
        parent_code: Optional[str] = None,
        category: Optional[AccountCategory] = None,
        description: Optional[str] = None,
        user_id: Optional[int] = None
    ) -> Tuple[Optional[Account], Optional[str]]:
        """创建科目"""
        with self.db.transaction() as session:
            # 检查编码是否已存在
            existing = session.query(Account).filter_by(
                organization_id=organization_id,
                code=code
            ).first()
            if existing:
                return None, f"科目编码 {code} 已存在"

            parent = None
            level = 1
            full_name = name

            # 处理上级科目
            if parent_code:
                parent = session.query(Account).filter_by(
                    organization_id=organization_id,
                    code=parent_code
                ).first()
                if not parent:
                    return None, f"上级科目 {parent_code} 不存在"

                level = parent.level + 1
                full_name = f"{parent.full_name}/{name}"

                # 上级科目不能再是末级
                parent.is_leaf = False

            account = Account(
                organization_id=organization_id,
                code=code,
                name=name,
                full_name=full_name,
                account_type=account_type,
                category=category,
                balance_direction=balance_direction,
                level=level,
                parent_id=parent.id if parent else None,
                is_leaf=True,
                description=description,
                is_active=True
            )
            session.add(account)
            session.flush()

            AuditService.log_data_change(
                action="account.create",
                user_id=user_id,
                organization_id=organization_id,
                resource_type="Account",
                resource_id=str(account.id),
                new_values={"code": code, "name": name}
            )

            return account, None

    def get_account_tree(self, organization_id: int) -> List[Dict]:
        """获取科目树形结构"""
        with self.db.transaction() as session:
            accounts = session.query(Account).filter_by(
                organization_id=organization_id,
                is_active=True
            ).order_by(Account.code).all()

            # 构建树形结构
            account_map = {}
            roots = []

            for acc in accounts:
                node = {
                    "id": acc.id,
                    "code": acc.code,
                    "name": acc.name,
                    "full_name": acc.full_name,
                    "type": acc.account_type.value,
                    "direction": acc.balance_direction.value,
                    "level": acc.level,
                    "is_leaf": acc.is_leaf,
                    "is_system": acc.is_system,
                    "children": []
                }
                account_map[acc.id] = node

                if acc.parent_id and acc.parent_id in account_map:
                    account_map[acc.parent_id]["children"].append(node)
                else:
                    roots.append(node)

            return roots

    # ==================== 凭证管理 ====================

    def create_voucher(
        self,
        organization_id: int,
        voucher_date: datetime,
        items: List[Dict],
        summary: Optional[str] = None,
        voucher_type: str = "记",
        transaction_id: Optional[int] = None,
        user_id: Optional[int] = None
    ) -> Tuple[Optional[Voucher], Optional[str]]:
        """
        创建会计凭证

        Args:
            items: [{"account_code": "1001", "direction": "DEBIT", "amount": 100.00, "summary": "..."}]
        """
        # 验证借贷平衡
        total_debit = Decimal('0')
        total_credit = Decimal('0')

        for item in items:
            amount = Decimal(str(item.get("amount", 0)))
            if item.get("direction") == "DEBIT":
                total_debit += amount
            else:
                total_credit += amount

        if total_debit != total_credit:
            return None, f"借贷不平衡: 借方 {total_debit}, 贷方 {total_credit}"

        if total_debit == 0:
            return None, "凭证金额不能为零"

        with self.db.transaction() as session:
            # 获取当前期间
            year = voucher_date.year
            month = voucher_date.month

            # 获取凭证号
            max_number = session.query(Voucher).filter_by(
                organization_id=organization_id,
                year=year,
                month=month,
                voucher_type=voucher_type
            ).count()
            voucher_number = max_number + 1

            # 创建凭证
            voucher = Voucher(
                organization_id=organization_id,
                voucher_type=voucher_type,
                voucher_number=voucher_number,
                voucher_date=voucher_date,
                year=year,
                month=month,
                summary=summary,
                transaction_id=transaction_id,
                created_by=user_id,
                status="DRAFT"
            )
            session.add(voucher)
            session.flush()

            # 创建分录
            for seq, item_data in enumerate(items):
                account = session.query(Account).filter_by(
                    organization_id=organization_id,
                    code=item_data["account_code"]
                ).first()

                if not account:
                    return None, f"科目 {item_data['account_code']} 不存在"

                if not account.is_leaf:
                    return None, f"科目 {item_data['account_code']} 不是末级科目，不能记账"

                direction = BalanceDirection(item_data["direction"])
                voucher_item = VoucherItem(
                    voucher_id=voucher.id,
                    account_id=account.id,
                    direction=direction,
                    amount=Decimal(str(item_data["amount"])),
                    summary=item_data.get("summary"),
                    auxiliary_customer=item_data.get("customer"),
                    auxiliary_supplier=item_data.get("supplier"),
                    auxiliary_project=item_data.get("project"),
                    auxiliary_department=item_data.get("department"),
                    seq=seq
                )
                session.add(voucher_item)

            AuditService.log_data_change(
                action="voucher.create",
                user_id=user_id,
                organization_id=organization_id,
                resource_type="Voucher",
                resource_id=str(voucher.id),
                new_values={"number": voucher_number, "amount": str(total_debit)}
            )

            return voucher, None

    def post_voucher(
        self,
        voucher_id: int,
        organization_id: int,
        user_id: int
    ) -> Tuple[bool, Optional[str]]:
        """过账凭证 (更新科目余额)"""
        with self.db.transaction() as session:
            voucher = session.query(Voucher).filter_by(
                id=voucher_id,
                organization_id=organization_id
            ).first()

            if not voucher:
                return False, "凭证不存在"

            if voucher.status == "POSTED":
                return False, "凭证已过账"

            # 更新科目余额
            for item in voucher.items:
                self._update_account_balance(
                    session,
                    organization_id,
                    item.account_id,
                    voucher.year,
                    voucher.month,
                    item.direction,
                    item.amount
                )

            voucher.status = "POSTED"
            voucher.posted_by = user_id
            voucher.posted_at = datetime.utcnow()

            AuditService.log(
                action="voucher.post",
                user_id=user_id,
                organization_id=organization_id,
                resource_type="Voucher",
                resource_id=str(voucher_id)
            )

            return True, None

    def _update_account_balance(
        self,
        session,
        organization_id: int,
        account_id: int,
        year: int,
        month: int,
        direction: BalanceDirection,
        amount: Decimal
    ):
        """更新科目余额"""
        balance = session.query(AccountBalance).filter_by(
            organization_id=organization_id,
            account_id=account_id,
            year=year,
            month=month
        ).first()

        if not balance:
            balance = AccountBalance(
                organization_id=organization_id,
                account_id=account_id,
                year=year,
                month=month
            )
            session.add(balance)

        if direction == BalanceDirection.DEBIT:
            balance.period_debit = (balance.period_debit or Decimal('0')) + amount
            balance.ytd_debit = (balance.ytd_debit or Decimal('0')) + amount
            balance.closing_debit = (balance.opening_debit or Decimal('0')) + (balance.period_debit or Decimal('0'))
        else:
            balance.period_credit = (balance.period_credit or Decimal('0')) + amount
            balance.ytd_credit = (balance.ytd_credit or Decimal('0')) + amount
            balance.closing_credit = (balance.opening_credit or Decimal('0')) + (balance.period_credit or Decimal('0'))

    # ==================== 余额查询 ====================

    def get_trial_balance(
        self,
        organization_id: int,
        year: int,
        month: int
    ) -> List[Dict]:
        """获取试算平衡表"""
        with self.db.transaction() as session:
            balances = session.query(AccountBalance).filter_by(
                organization_id=organization_id,
                year=year,
                month=month
            ).all()

            result = []
            total_opening_debit = Decimal('0')
            total_opening_credit = Decimal('0')
            total_period_debit = Decimal('0')
            total_period_credit = Decimal('0')
            total_closing_debit = Decimal('0')
            total_closing_credit = Decimal('0')

            for bal in balances:
                account = bal.account
                row = {
                    "account_code": account.code,
                    "account_name": account.name,
                    "opening_debit": float(bal.opening_debit or 0),
                    "opening_credit": float(bal.opening_credit or 0),
                    "period_debit": float(bal.period_debit or 0),
                    "period_credit": float(bal.period_credit or 0),
                    "closing_debit": float(bal.closing_debit or 0),
                    "closing_credit": float(bal.closing_credit or 0),
                }
                result.append(row)

                total_opening_debit += bal.opening_debit or Decimal('0')
                total_opening_credit += bal.opening_credit or Decimal('0')
                total_period_debit += bal.period_debit or Decimal('0')
                total_period_credit += bal.period_credit or Decimal('0')
                total_closing_debit += bal.closing_debit or Decimal('0')
                total_closing_credit += bal.closing_credit or Decimal('0')

            # 添加合计行
            result.append({
                "account_code": "",
                "account_name": "合计",
                "opening_debit": float(total_opening_debit),
                "opening_credit": float(total_opening_credit),
                "period_debit": float(total_period_debit),
                "period_credit": float(total_period_credit),
                "closing_debit": float(total_closing_debit),
                "closing_credit": float(total_closing_credit),
                "is_balanced": total_period_debit == total_period_credit
            })

            return result


# 单例
_accounting_service = None


def get_accounting_service() -> AccountingService:
    """获取会计服务单例"""
    global _accounting_service
    if _accounting_service is None:
        _accounting_service = AccountingService()
    return _accounting_service
