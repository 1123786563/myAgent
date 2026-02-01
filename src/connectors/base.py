"""
数据连接器基类
Data Connector Base - Abstract interface for payment/bank integrations
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from datetime import datetime, date
from decimal import Decimal
from enum import Enum
from dataclasses import dataclass
from infra.logger import get_logger

log = get_logger("Connector")


class ConnectorStatus(Enum):
    """连接器状态"""
    DISCONNECTED = "DISCONNECTED"
    CONNECTED = "CONNECTED"
    SYNCING = "SYNCING"
    ERROR = "ERROR"


class TransactionType(Enum):
    """交易类型"""
    INCOME = "INCOME"       # 收入
    EXPENSE = "EXPENSE"     # 支出
    TRANSFER = "TRANSFER"   # 转账
    REFUND = "REFUND"       # 退款


@dataclass
class ConnectorTransaction:
    """连接器交易数据结构"""
    external_id: str                    # 外部交易ID
    transaction_type: TransactionType   # 交易类型
    amount: Decimal                     # 金额
    currency: str                       # 货币
    counterparty: str                   # 对方名称
    description: str                    # 描述/摘要
    transaction_time: datetime          # 交易时间
    status: str                         # 状态
    raw_data: Dict = None               # 原始数据
    fee: Decimal = Decimal('0')         # 手续费
    counterparty_account: str = None    # 对方账号
    order_id: str = None                # 订单号
    category: str = None                # 分类


@dataclass
class ConnectorConfig:
    """连接器配置"""
    connector_type: str
    name: str
    credentials: Dict[str, str]
    settings: Dict[str, Any] = None
    is_enabled: bool = True


class BaseConnector(ABC):
    """
    数据连接器基类

    所有支付/银行连接器必须继承此类
    """

    def __init__(self, config: ConnectorConfig):
        self.config = config
        self.status = ConnectorStatus.DISCONNECTED
        self.last_sync_time: Optional[datetime] = None
        self.error_message: Optional[str] = None

    @property
    @abstractmethod
    def connector_type(self) -> str:
        """连接器类型标识"""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """显示名称"""
        pass

    @abstractmethod
    async def connect(self) -> bool:
        """
        建立连接/验证凭证

        Returns:
            是否连接成功
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """断开连接"""
        pass

    @abstractmethod
    async def test_connection(self) -> Dict[str, Any]:
        """
        测试连接

        Returns:
            {'success': bool, 'message': str, 'account_info': dict}
        """
        pass

    @abstractmethod
    async def fetch_transactions(
        self,
        start_date: date,
        end_date: date,
        page: int = 1,
        page_size: int = 100
    ) -> List[ConnectorTransaction]:
        """
        获取交易记录

        Args:
            start_date: 开始日期
            end_date: 结束日期
            page: 页码
            page_size: 每页数量

        Returns:
            交易列表
        """
        pass

    @abstractmethod
    async def fetch_balance(self) -> Dict[str, Decimal]:
        """
        获取账户余额

        Returns:
            {'available': Decimal, 'frozen': Decimal, 'total': Decimal}
        """
        pass

    async def sync_transactions(
        self,
        start_date: date,
        end_date: date,
        callback=None
    ) -> Dict[str, Any]:
        """
        同步交易记录

        Args:
            start_date: 开始日期
            end_date: 结束日期
            callback: 进度回调函数

        Returns:
            同步结果统计
        """
        self.status = ConnectorStatus.SYNCING
        total_count = 0
        new_count = 0
        error_count = 0

        try:
            page = 1
            while True:
                transactions = await self.fetch_transactions(
                    start_date, end_date, page=page
                )

                if not transactions:
                    break

                for tx in transactions:
                    total_count += 1
                    try:
                        if callback:
                            is_new = await callback(tx)
                            if is_new:
                                new_count += 1
                    except Exception as e:
                        log.error(f"Error processing transaction {tx.external_id}: {e}")
                        error_count += 1

                page += 1

            self.last_sync_time = datetime.now()
            self.status = ConnectorStatus.CONNECTED

            return {
                'success': True,
                'total_count': total_count,
                'new_count': new_count,
                'error_count': error_count,
                'sync_time': self.last_sync_time.isoformat()
            }

        except Exception as e:
            self.status = ConnectorStatus.ERROR
            self.error_message = str(e)
            log.error(f"Sync failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'total_count': total_count,
                'new_count': new_count,
                'error_count': error_count
            }

    def get_status(self) -> Dict[str, Any]:
        """获取连接器状态"""
        return {
            'connector_type': self.connector_type,
            'display_name': self.display_name,
            'status': self.status.value,
            'last_sync_time': self.last_sync_time.isoformat() if self.last_sync_time else None,
            'error_message': self.error_message,
            'is_enabled': self.config.is_enabled
        }


class ConnectorRegistry:
    """连接器注册表"""

    _connectors: Dict[str, type] = {}

    @classmethod
    def register(cls, connector_class: type):
        """注册连接器类"""
        instance = connector_class.__new__(connector_class)
        connector_type = instance.connector_type
        cls._connectors[connector_type] = connector_class
        log.info(f"Registered connector: {connector_type}")
        return connector_class

    @classmethod
    def get(cls, connector_type: str) -> Optional[type]:
        """获取连接器类"""
        return cls._connectors.get(connector_type)

    @classmethod
    def list_available(cls) -> List[Dict[str, str]]:
        """列出所有可用连接器"""
        result = []
        for connector_type, connector_class in cls._connectors.items():
            instance = connector_class.__new__(connector_class)
            result.append({
                'type': connector_type,
                'name': instance.display_name
            })
        return result

    @classmethod
    def create(cls, config: ConnectorConfig) -> Optional[BaseConnector]:
        """创建连接器实例"""
        connector_class = cls.get(config.connector_type)
        if connector_class:
            return connector_class(config)
        return None
