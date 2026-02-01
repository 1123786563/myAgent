from connectors.base_connector import BaseConnector
from infra.logger import get_logger

log = get_logger("ShopifyConnector")

class ShopifyConnector(BaseConnector):
    """
    Shopify 电商平台连接器实现
    """
    def __init__(self):
        super().__init__("Shopify-Live")

    def fetch_raw_data(self, params=None):
        log.info("从 Shopify API 获取订单流水...")
        return [
            {"order_id": "SH-1001", "total": 299.0, "currency": "USD", "created_at": "2025-03-24T10:00:00Z"},
            {"order_id": "SH-1002", "total": 59.0, "currency": "USD", "created_at": "2025-03-24T11:30:00Z"}
        ]

    def transform_to_ledger(self, raw_data):
        ledger_entries = []
        for item in raw_data:
            ledger_entries.append({
                "vendor": "Shopify-Customer",
                "amount": item['total'] * 7.2,
                "category": "1122-01 (应收账款-电商销售)",
                "trace_id": f"SHOPIFY-{item['order_id']}",
                "source": "CONNECTOR_SHOPIFY"
            })
        return ledger_entries
