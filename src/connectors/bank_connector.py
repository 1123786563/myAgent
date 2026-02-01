"""
银行对账连接器
Bank Statement Connector - Import bank statements from various formats
"""

import csv
import io
from datetime import datetime, date
from decimal import Decimal
from typing import Dict, List, Any, Optional
from connectors.base import (
    BaseConnector, ConnectorConfig, ConnectorTransaction,
    TransactionType, ConnectorStatus, ConnectorRegistry
)
from infra.logger import get_logger

log = get_logger("BankConnector")


@ConnectorRegistry.register
class BankStatementConnector(BaseConnector):
    """
    银行对账单连接器

    支持导入银行对账单文件 (CSV/Excel)
    支持主要银行格式: 工商银行、建设银行、招商银行等
    """

    @property
    def connector_type(self) -> str:
        return "bank_statement"

    @property
    def display_name(self) -> str:
        return "银行对账单"

    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        self.bank_type = config.settings.get("bank_type", "generic")
        self.account_number = config.credentials.get("account_number")
        self._transactions: List[ConnectorTransaction] = []

    async def connect(self) -> bool:
        """银行对账单不需要实时连接"""
        self.status = ConnectorStatus.CONNECTED
        return True

    async def disconnect(self) -> None:
        """断开连接"""
        self.status = ConnectorStatus.DISCONNECTED

    async def test_connection(self) -> Dict[str, Any]:
        """测试连接"""
        return {
            "success": True,
            "message": "银行对账单导入器就绪",
            "account_info": {
                "bank_type": self.bank_type,
                "account_number": self.account_number
            }
        }

    async def fetch_transactions(
        self,
        start_date: date,
        end_date: date,
        page: int = 1,
        page_size: int = 100
    ) -> List[ConnectorTransaction]:
        """获取已导入的交易记录"""
        filtered = [
            tx for tx in self._transactions
            if start_date <= tx.transaction_time.date() <= end_date
        ]

        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size

        return filtered[start_idx:end_idx]

    async def fetch_balance(self) -> Dict[str, Decimal]:
        """银行余额需要从对账单中获取"""
        return {
            "available": Decimal("0"),
            "frozen": Decimal("0"),
            "total": Decimal("0")
        }

    def import_from_csv(self, content: str, encoding: str = "utf-8") -> int:
        """
        从 CSV 文件导入银行对账单

        Args:
            content: CSV 文件内容
            encoding: 文件编码

        Returns:
            导入的交易数量
        """
        reader = csv.DictReader(io.StringIO(content))
        count = 0

        for row in reader:
            try:
                tx = self._parse_csv_row(row)
                if tx:
                    self._transactions.append(tx)
                    count += 1
            except Exception as e:
                log.warning(f"Failed to parse row: {e}")

        log.info(f"Imported {count} transactions from CSV")
        return count

    def import_from_icbc(self, content: str) -> int:
        """导入工商银行对账单"""
        return self._import_with_mapping(content, {
            "transaction_id": "交易流水号",
            "date": "交易日期",
            "time": "交易时间",
            "amount": "交易金额",
            "balance": "账户余额",
            "counterparty": "对方户名",
            "counterparty_account": "对方账号",
            "description": "摘要"
        })

    def import_from_ccb(self, content: str) -> int:
        """导入建设银行对账单"""
        return self._import_with_mapping(content, {
            "transaction_id": "流水号",
            "date": "交易日期",
            "amount": "发生额",
            "balance": "余额",
            "counterparty": "对方名称",
            "description": "摘要"
        })

    def import_from_cmb(self, content: str) -> int:
        """导入招商银行对账单"""
        return self._import_with_mapping(content, {
            "transaction_id": "流水号",
            "date": "交易日期",
            "debit": "借方发生额",
            "credit": "贷方发生额",
            "balance": "余额",
            "counterparty": "对方户名",
            "description": "摘要"
        })

    def _import_with_mapping(self, content: str, mapping: Dict[str, str]) -> int:
        """使用字段映射导入"""
        reader = csv.DictReader(io.StringIO(content))
        count = 0

        for row in reader:
            try:
                # 解析日期
                date_str = row.get(mapping.get("date", ""), "")
                time_str = row.get(mapping.get("time", ""), "00:00:00")

                if not date_str:
                    continue

                # 尝试多种日期格式
                tx_time = None
                for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日"]:
                    try:
                        tx_time = datetime.strptime(f"{date_str} {time_str}", f"{fmt} %H:%M:%S")
                        break
                    except ValueError:
                        try:
                            tx_time = datetime.strptime(date_str, fmt)
                            break
                        except ValueError:
                            continue

                if not tx_time:
                    continue

                # 解析金额
                amount_str = row.get(mapping.get("amount", ""), "0")
                debit_str = row.get(mapping.get("debit", ""), "0")
                credit_str = row.get(mapping.get("credit", ""), "0")

                if amount_str and amount_str != "0":
                    amount = Decimal(amount_str.replace(",", "").replace("￥", ""))
                    tx_type = TransactionType.INCOME if amount > 0 else TransactionType.EXPENSE
                    amount = abs(amount)
                elif debit_str and debit_str != "0" and debit_str.strip():
                    amount = Decimal(debit_str.replace(",", "").replace("￥", ""))
                    tx_type = TransactionType.EXPENSE
                elif credit_str and credit_str != "0" and credit_str.strip():
                    amount = Decimal(credit_str.replace(",", "").replace("￥", ""))
                    tx_type = TransactionType.INCOME
                else:
                    continue

                tx = ConnectorTransaction(
                    external_id=row.get(mapping.get("transaction_id", ""), f"BANK_{count}"),
                    transaction_type=tx_type,
                    amount=amount,
                    currency="CNY",
                    counterparty=row.get(mapping.get("counterparty", ""), ""),
                    counterparty_account=row.get(mapping.get("counterparty_account", ""), ""),
                    description=row.get(mapping.get("description", ""), ""),
                    transaction_time=tx_time,
                    status="COMPLETED",
                    raw_data=dict(row)
                )

                self._transactions.append(tx)
                count += 1

            except Exception as e:
                log.warning(f"Failed to parse bank row: {e}")

        log.info(f"Imported {count} bank transactions")
        return count

    def _parse_csv_row(self, row: Dict) -> Optional[ConnectorTransaction]:
        """解析通用 CSV 行"""
        # 尝试识别常见字段
        tx_id = row.get("transaction_id") or row.get("流水号") or row.get("交易流水号")
        date_str = row.get("date") or row.get("交易日期") or row.get("日期")
        amount_str = row.get("amount") or row.get("金额") or row.get("交易金额")
        counterparty = row.get("counterparty") or row.get("对方户名") or row.get("对方名称")
        description = row.get("description") or row.get("摘要") or row.get("备注")

        if not date_str or not amount_str:
            return None

        # 解析日期
        tx_time = None
        for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"]:
            try:
                tx_time = datetime.strptime(date_str, fmt)
                break
            except ValueError:
                continue

        if not tx_time:
            return None

        # 解析金额
        amount = Decimal(str(amount_str).replace(",", "").replace("￥", ""))
        tx_type = TransactionType.INCOME if amount > 0 else TransactionType.EXPENSE

        return ConnectorTransaction(
            external_id=tx_id or f"CSV_{hash(str(row))}",
            transaction_type=tx_type,
            amount=abs(amount),
            currency="CNY",
            counterparty=counterparty or "",
            description=description or "",
            transaction_time=tx_time,
            status="COMPLETED",
            raw_data=row
        )
