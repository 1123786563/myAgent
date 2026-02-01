"""
支付宝连接器
Alipay Connector - Fetch transactions from Alipay merchant account
"""

import hashlib
import json
from datetime import datetime, date
from decimal import Decimal
from typing import Dict, List, Any, Optional
from connectors.base import (
    BaseConnector, ConnectorConfig, ConnectorTransaction,
    TransactionType, ConnectorStatus, ConnectorRegistry
)
from infra.logger import get_logger

log = get_logger("AlipayConnector")


@ConnectorRegistry.register
class AlipayConnector(BaseConnector):
    """
    支付宝连接器

    支持获取商户账单和资金流水
    需要配置: app_id, private_key, alipay_public_key
    """

    @property
    def connector_type(self) -> str:
        return "alipay"

    @property
    def display_name(self) -> str:
        return "支付宝"

    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        self.app_id = config.credentials.get("app_id")
        self.private_key = config.credentials.get("private_key")
        self.alipay_public_key = config.credentials.get("alipay_public_key")
        self.gateway_url = config.settings.get("gateway_url", "https://openapi.alipay.com/gateway.do")
        self._client = None

    async def connect(self) -> bool:
        """建立连接"""
        try:
            # 实际生产环境需要使用 alipay-sdk-python
            # from alipay import AliPay
            # self._client = AliPay(
            #     appid=self.app_id,
            #     app_private_key_string=self.private_key,
            #     alipay_public_key_string=self.alipay_public_key,
            # )

            # 模拟连接
            if not self.app_id or not self.private_key:
                raise ValueError("Missing app_id or private_key")

            self.status = ConnectorStatus.CONNECTED
            log.info(f"Alipay connector connected: {self.app_id}")
            return True

        except Exception as e:
            self.status = ConnectorStatus.ERROR
            self.error_message = str(e)
            log.error(f"Alipay connection failed: {e}")
            return False

    async def disconnect(self) -> None:
        """断开连接"""
        self._client = None
        self.status = ConnectorStatus.DISCONNECTED

    async def test_connection(self) -> Dict[str, Any]:
        """测试连接"""
        try:
            connected = await self.connect()
            if connected:
                # 实际应调用 alipay.fund.account.query
                return {
                    "success": True,
                    "message": "连接成功",
                    "account_info": {
                        "app_id": self.app_id,
                        "status": "ACTIVE"
                    }
                }
            else:
                return {
                    "success": False,
                    "message": self.error_message
                }
        except Exception as e:
            return {
                "success": False,
                "message": str(e)
            }

    async def fetch_transactions(
        self,
        start_date: date,
        end_date: date,
        page: int = 1,
        page_size: int = 100
    ) -> List[ConnectorTransaction]:
        """
        获取交易记录

        实际生产环境调用:
        - alipay.data.dataservice.bill.downloadurl.query (下载账单)
        - 或 alipay.trade.query (查询单笔交易)
        """
        transactions = []

        # 模拟实现 - 实际需要调用支付宝API
        # response = self._client.api_alipay_data_dataservice_bill_downloadurl_query(
        #     bill_type="trade",
        #     bill_date=start_date.strftime("%Y-%m-%d")
        # )

        log.info(f"Fetching Alipay transactions: {start_date} to {end_date}, page {page}")

        # 返回空列表，实际实现需要解析账单文件
        return transactions

    async def fetch_balance(self) -> Dict[str, Decimal]:
        """
        获取账户余额

        调用 alipay.fund.account.query
        """
        # 模拟实现
        # response = self._client.api_alipay_fund_account_query()

        return {
            "available": Decimal("0"),
            "frozen": Decimal("0"),
            "total": Decimal("0")
        }

    def _parse_transaction(self, raw: Dict) -> ConnectorTransaction:
        """解析支付宝交易记录"""
        # 判断交易类型
        trade_type = raw.get("trans_code", "")
        if trade_type in ["6001", "6002"]:  # 收款
            tx_type = TransactionType.INCOME
        elif trade_type in ["6051", "6052"]:  # 退款
            tx_type = TransactionType.REFUND
        else:
            tx_type = TransactionType.EXPENSE

        return ConnectorTransaction(
            external_id=raw.get("trade_no", ""),
            transaction_type=tx_type,
            amount=Decimal(str(raw.get("total_amount", 0))),
            currency="CNY",
            counterparty=raw.get("buyer_logon_id", ""),
            description=raw.get("subject", ""),
            transaction_time=datetime.strptime(
                raw.get("gmt_payment", ""),
                "%Y-%m-%d %H:%M:%S"
            ) if raw.get("gmt_payment") else datetime.now(),
            status=raw.get("trade_status", ""),
            raw_data=raw,
            fee=Decimal(str(raw.get("point_amount", 0))),
            order_id=raw.get("out_trade_no", "")
        )
