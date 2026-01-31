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

    def _analyze_vendor_price_clustering(self, vendor, category, current_price):
        """
        智能供应商洞察：历史价格聚类分析 (F3.3.5)
        当单价偏离历史中位数 15% 时触发预警。
        """
        try:
            # 1. 从 DB 获取该供应商该科目的历史单价 (模拟聚合查询)
            sql = """
                SELECT amount FROM transactions 
                WHERE vendor = ? AND category = ? AND status = 'AUDITED'
                ORDER BY created_at DESC LIMIT 20
            """
            with self.db.transaction("DEFERRED") as conn:
                rows = conn.execute(sql, (vendor, category)).fetchall()
                prices = [float(r['amount']) for r in rows]
            
            if len(prices) < 3: return True, 0 # 样本不足，不预警

            # 2. 计算中位数与偏离度
            import statistics
            median_price = statistics.median(prices)
            deviation = abs(current_price - median_price) / (median_price + 1)
            
            if deviation > 0.15:
                log.warning(f"供应商价格异常预警: {vendor} | 当前: {current_price} | 历史中位: {median_price:.2f} | 偏离: {deviation:.1%}")
                return False, deviation
                
            return True, deviation
        except Exception as e:
            log.error(f"价格聚类分析失败: {e}")
            return True, 0

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

        # 1. 税负率偏离度分析
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

        # 4. 供应商价格聚类分析 (F3.3.5)
        price_ok, dev = self._analyze_vendor_price_clustering(vendor, category, amount)
        if not price_ok:
            warnings.append(f"供应商价格异常：偏离历史均值 {dev:.1%}")
            risk_level = "MEDIUM"

        # 5. 公转私/敏感收款方检测
        if any(kw in vendor for kw in ["个人", "劳务", "小明"]): # 简化模拟
            warnings.append(f"潜在公转私风险：收款方 [{vendor}] 可能为自然人")
            if risk_level != "HIGH": risk_level = "MEDIUM"

        decision = "WARNING" if warnings else "PASS"
        if is_blocked: decision = "BLOCK"

        result = {
            "decision": decision,
            "risk_level": risk_level,
            "warnings": warnings,
            "timestamp": self.db.get_now() if hasattr(self.db, 'get_now') else "2025-03-24"
        }

        log.info(f"Sentinel 巡检结束: Decision={decision} | Warnings={len(warnings)}")
        return LedgerMsg.create(self.name, result, action="SENTINEL_CHECK", trace_id=trace_id)

    def _get_monthly_stats(self):
        """模拟获取财务指标"""
        # 实际应从 DB 聚合查询
        return {"revenue": 1000000, "vat_net": 20000}

if __name__ == "__main__":
    sentinel = SentinelAgent("Sentinel-01")
    test_msg = {"content": {"amount": 60000, "category": "无票支出", "vendor": "某娱乐中心"}, "trace_id": "test-999"}
    print(sentinel.reply(test_msg))
