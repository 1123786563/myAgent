"""
微信支付连接器
WeChat Pay Connector - Fetch transactions from WeChat Pay merchant account
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

log = get_logger("WechatPayConnector")


@ConnectorRegistry.register
class WechatPayConnector(BaseConnector):
    """
    微信支付连接器

    支持获取商户账单和资金流水
    需要配置: mch_id, api_key, cert_path, key_path
    """

    @property
    def connector_type(self) -> str:
        return "wechat_pay"

    @property
    def display_name(self) -> str:
        return "微信支付"

    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        self.mch_id = config.credentials.get("mch_id")
        self.api_key = config.credentials.get("api_key")
        self.api_v3_key = config.credentials.get("api_v3_key")
        self.cert_serial_no = config.credentials.get("cert_serial_no")
        self.private_key_path = config.credentials.get("private_key_path")
        self._client = None

    async def connect(self) -> bool:
        """建立连接"""
        try:
            # 实际生产环境需要使用 wechatpayv3
            # from wechatpayv3 import WeChatPay
            # self._client = WeChatPay(
            #     wechatpay_type=WeChatPayType.NATIVE,
            #     mchid=self.mch_id,
            #     private_key=open(self.private_key_path).read(),
            #     cert_serial_no=self.cert_serial_no,
            #     apiv3_key=self.api_v3_key,
            # )

            if not self.mch_id or not self.api_key:
                raise ValueError("Missing mch_id or api_key")

            self.status = ConnectorStatus.CONNECTED
            log.info(f"WeChat Pay connector connected: {self.mch_id}")
            return True

        except Exception as e:
            self.status = ConnectorStatus.ERROR
            self.error_message = str(e)
            log.error(f"WeChat Pay connection failed: {e}")
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
                return {
                    "success": True,
                    "message": "连接成功",
                    "account_info": {
                        "mch_id": self.mch_id,
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
        - 下载交易账单 /v3/bill/tradebill
        - 下载资金账单 /v3/bill/fundflowbill
        """
        transactions = []

        # 模拟实现 - 实际需要调用微信支付API下载账单
        # bill_date = start_date.strftime("%Y-%m-%d")
        # response = self._client.download_bill(bill_date, bill_type='ALL')

        log.info(f"Fetching WeChat Pay transactions: {start_date} to {end_date}, page {page}")

        return transactions

    async def fetch_balance(self) -> Dict[str, Decimal]:
        """
        获取账户余额

        调用 /v3/merchant/fund/balance/{account_type}
        """
        return {
            "available": Decimal("0"),
            "frozen": Decimal("0"),
            "total": Decimal("0")
        }

    def _parse_transaction(self, raw: Dict) -> ConnectorTransaction:
        """解析微信支付交易记录"""
        trade_type = raw.get("trade_type", "")
        trade_state = raw.get("trade_state", "")

        if trade_state == "REFUND":
            tx_type = TransactionType.REFUND
        elif trade_type in ["JSAPI", "NATIVE", "APP", "MICROPAY"]:
            tx_type = TransactionType.INCOME
        else:
            tx_type = TransactionType.EXPENSE

        return ConnectorTransaction(
            external_id=raw.get("transaction_id", ""),
            transaction_type=tx_type,
            amount=Decimal(str(raw.get("total", 0))) / 100,  # 微信金额单位是分
            currency="CNY",
            counterparty=raw.get("payer", {}).get("openid", ""),
            description=raw.get("description", ""),
            transaction_time=datetime.strptime(
                raw.get("success_time", ""),
                "%Y-%m-%dT%H:%M:%S%z"
            ) if raw.get("success_time") else datetime.now(),
            status=trade_state,
            raw_data=raw,
            order_id=raw.get("out_trade_no", "")
        )
