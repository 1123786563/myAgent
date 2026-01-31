from bus_init import LedgerMsg
from agentscope.agents import AgentBase
from logger import get_logger
from db_helper import DBHelper
import json

log = get_logger("SentinelAgent")

class SentinelAgent(AgentBase):
    """
    税务合规哨兵 (The Sentinel)
    模拟金税四期巡检逻辑：进销项匹配、税负率预警、红线阻断。
    """
    def __init__(self, name):
        super().__init__(name=name)
        self.db = DBHelper()
        # 预设行业平均税负率 (示例: 3%)
        self.industry_tax_burden = 0.03
        # 合规红线金额
        self.compliance_redline = 50000

    def reply(self, x: dict = None) -> dict:
        proposal = x.get("content", {})
        amount = float(proposal.get("amount", 0))
        category = proposal.get("category", "")
        vendor = proposal.get("vendor", "Unknown")
        trace_id = x.get("trace_id", "Unknown")
        
        log.info(f"Sentinel 启动合规巡检: TraceID={trace_id} | Amount={amount}")
        
        warnings = []
        is_blocked = False
        risk_level = "LOW"

        # 1. 税负率偏离度分析 (模拟)
        # 获取本月累计销项与进项 (此处简化为从 DB 查询)
        stats = self._get_monthly_stats()
        current_tax_burden = stats['vat_net'] / (stats['revenue'] + 1)
        if current_tax_burden < self.industry_tax_burden * 0.7:
            warnings.append(f"税负率过低({current_tax_burden:.2%})，低于行业平均值 {self.industry_tax_burden:.2%}")
            risk_level = "MEDIUM"

        # 2. 异常大额无票预警
        if amount > self.compliance_redline and "无票" in category:
            warnings.append(f"触发合规红线：大额无票支出({amount} > {self.compliance_redline})")
            risk_level = "HIGH"
            is_blocked = True

        # 3. 进销项匹配度校验
        if not self._check_business_relevance(vendor, category):
            warnings.append(f"业务关联度可疑：供应商 {vendor} 与科目 {category} 属性不匹配")
            risk_level = "MEDIUM"

        decision = "WARNING" if warnings else "PASS"
        if is_blocked: decision = "BLOCK"

        result = {
            "decision": decision,
            "risk_level": risk_level,
            "warnings": warnings,
            "timestamp": self.db.get_now()
        }

        log.info(f"Sentinel 巡检结束: Decision={decision} | Warnings={len(warnings)}")
        return LedgerMsg.create(self.name, result, action="SENTINEL_CHECK", trace_id=trace_id)

    def _get_monthly_stats(self):
        """模拟获取财务指标"""
        # 实际应从 DB 聚合查询
        return {"revenue": 1000000, "vat_net": 20000}

    def _check_business_relevance(self, vendor, category):
        """简单的供应商与业务匹配校验"""
        # 示例：如果供应商包含 '餐馆' 但科目是 '办公用品'，触发预警
        suspicious_pairs = [
            ("餐饮", "办公用品"),
            ("加油站", "差旅费-打车"),
            ("娱乐", "研发支出")
        ]
        for v_kw, c_kw in suspicious_pairs:
            if v_kw in vendor and c_kw in category:
                return False
        return True

if __name__ == "__main__":
    sentinel = SentinelAgent("Sentinel-01")
    test_msg = {"content": {"amount": 60000, "category": "无票支出", "vendor": "某娱乐中心"}, "trace_id": "test-999"}
    print(sentinel.reply(test_msg))
