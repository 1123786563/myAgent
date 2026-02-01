from utils.decimal_utils import to_decimal
from infra.logger import get_logger

log = get_logger("CollectorParsers")

class BankStatementParser:
    """[Optimization 2] Strategy Pattern for Bank Statement Parsing"""
    def parse(self, df) -> list:
        raise NotImplementedError
    @classmethod
    def match(cls, columns) -> bool:
        return False

class AliPayParser(BankStatementParser):
    @classmethod
    def match(cls, columns):
        return "业务流水号" in columns and "对方名称" in columns
    def parse(self, df) -> list:
        batch = []
        for _, row in df.iterrows():
            try:
                if row.get("收/支", "") == "支出":
                    amt = to_decimal(str(row.get("金额", 0)).replace(",", ""))
                    batch.append({"amount": abs(amt), "vendor_keyword": str(row.get("对方名称", "Unknown")).strip(), "source": "ALIPAY"})
            except: continue
        return batch

class WeChatParser(BankStatementParser):
    @classmethod
    def match(cls, columns):
        return "交易单号" in columns and "当前状态" in columns and "交易类型" in columns
    def parse(self, df) -> list:
        batch = []
        for _, row in df.iterrows():
            try:
                if row.get("收/支", "") == "支出":
                    amt = to_decimal(str(row.get("金额(元)", 0)).replace("¥", "").replace(",", ""))
                    batch.append({"amount": abs(amt), "vendor_keyword": str(row.get("交易对方", "Unknown")).strip(), "source": "WECHAT"})
            except: continue
        return batch

class GenericParser(BankStatementParser):
    def __init__(self):
        from core.config_manager import ConfigManager
        mapping = ConfigManager.get("bank_mapping.default", {})
        self.col_vendor = mapping.get("vendor_col", "对方户名")
        self.col_amount = mapping.get("amount_col", "金额")
    @classmethod
    def match(cls, columns):
        return True
    def parse(self, df) -> list:
        batch = []
        if self.col_vendor not in df.columns or self.col_amount not in df.columns: return []
        for _, row in df.iterrows():
            try:
                amt = to_decimal(str(row.get(self.col_amount, 0)).replace(",", "").replace("¥", ""))
                if amt != 0:
                    batch.append({"amount": abs(amt), "vendor_keyword": str(row.get(self.col_vendor, "未知商户")).strip(), "source": "BANK_FLOW"})
            except: continue
        return batch
