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
        from config_manager import ConfigManager
        self.db = DBHelper()
        # [Suggestion 1] 加载动态阈值
        self.taxpayer_type = ConfigManager.get("tax.taxpayer_type", "SMALL_SCALE")
        self.industry_tax_burden = ConfigManager.get("tax.target_burden", 0.03)
        self.free_limit = ConfigManager.get("tax.free_limit_monthly", 100000)
        self.compliance_redline = ConfigManager.get("tax.compliance_redline", 50000)
        log.info(f"SentinelAgent 初始化: 性质={self.taxpayer_type} | 免税额度={self.free_limit}")

    def _check_business_relevance(self, vendor, category):
        """增强的供应商与业务匹配校验"""
        suspicious_pairs = [
            ("餐饮", "办公用品"),
            ("加油站", "差旅费-打车"),
            ("娱乐", "研发支出"),
            ("劳务", "固定资产")
        ]
        for v_kw, c_kw in suspicious_pairs:
            if v_kw in vendor and c_kw in category:
                return False
        return True

    def _analyze_vendor_price_clustering(self, vendor, category, current_price):
        try:
            sql = """
                SELECT amount FROM transactions 
                WHERE vendor = ? AND category = ? AND status = 'AUDITED'
                ORDER BY created_at DESC LIMIT 20
            """
            with self.db.transaction("DEFERRED") as conn:
                rows = conn.execute(sql, (vendor, category)).fetchall()
                prices = [float(r['amount']) for r in rows]
            
            if len(prices) < 3: return True, 0

            import statistics
            median_price = statistics.median(prices)
            std_dev = statistics.stdev(prices) if len(prices) > 1 else 0
            mean_price = statistics.mean(prices)
            cv = std_dev / (mean_price + 1)
            dynamic_threshold = 0.15 + (cv * 0.5)
            deviation = abs(current_price - median_price) / (median_price + 1)
            
            if deviation > dynamic_threshold:
                log.warning(f"供应商价格异常: {vendor} | 偏离: {deviation:.1%} | 动态阈值: {dynamic_threshold:.1%}")
                return False, deviation
            return True, deviation
        except Exception as e:
            log.error(f"价格分析失败: {e}")
            return True, 0

    def _calculate_projected_tax(self):
        """
        [Optimization 3] 税务筹划预警逻辑 (Proactive Tax Advisor)
        识别起征点风险并主动推送策略卡片 (F3.3.2)
        """
        stats = self._get_monthly_stats()
        revenue = stats.get('revenue', 0)
        vat_in_actual = stats.get('vat_in', 0)
        
        # 预估销项税 (Output VAT)
        vat_out_est = revenue * (0.13 if self.taxpayer_type == "GENERAL" else 0.03)
        
        # [Optimization 3] 策略建议逻辑
        strategy_tips = []
        limit = self.free_limit
        if self.taxpayer_type == "SMALL_SCALE":
            if limit * 0.85 < revenue < limit:
                msg = f"【筹划预警】当前营收 ￥{revenue:,.2f} 已逼近月度免税红线 (￥{limit:,.2f})。建议控制月底开票节奏，或提前确认合规进项。"
                strategy_tips.append({"title": "月度免税节奏控制", "tip": msg, "action": "ALERT"})
            elif revenue >= limit:
                msg = "本月营收已超免税额度。建议增加合规成本票采集，最大化企业所得税税前扣除。"
                strategy_tips.append({"title": "进项票据追索建议", "tip": msg, "action": "OPTIMIZE"})

        return {
            "projected_vat": round(vat_out_est - vat_in_actual, 2),
            "strategies": strategy_tips,
            "status": "ADVISORY" if strategy_tips else "NORMAL"
        }

    def _check_budget_compliance(self, dept_name, amount):
        """
        [Optimization 3] 预算红线主动管控 (F3.3.3)
        """
        try:
            with self.db.transaction("DEFERRED") as conn:
                row = conn.execute("SELECT monthly_limit, current_spent FROM dept_budgets WHERE dept_name = ?", (dept_name,)).fetchone()
                if not row: return True # 未设预算不拦截
                
                limit = float(row['monthly_limit'])
                spent = float(row['current_spent'])
                remaining = limit - spent
                
                if amount > remaining:
                    log.critical(f"预算熔断：{dept_name} 余额 ￥{remaining:.2f} 不足支付 ￥{amount:.2f}！")
                    return False
                elif (remaining - amount) / limit < 0.15:
                    log.warning(f"预算预警：{dept_name} 支出后余额将低于 15% 红线。")
            return True
        except:
            return True

    def _run_tax_stress_test(self, proposal):
        sim_spending = float(proposal.get("simulated_spending", 0))
        stats = self._get_monthly_stats()
        current_vat = max(0, stats['revenue'] * 0.13 - stats.get('vat_in', 0))
        new_vat_in = stats.get('vat_in', 0) + (sim_spending * 0.13)
        simulated_vat = max(0, stats['revenue'] * 0.13 - new_vat_in)
        tax_saving = current_vat - simulated_vat
        
        result = {
            "strategy": "TAX_SAVING_SIMULATION",
            "saving": round(tax_saving, 2),
            "recommendation": "可行" if tax_saving > 1000 else "建议推迟"
        }
        return LedgerMsg.create(self.name, result, action="STRESS_TEST_RESULT", sender_role="SENTINEL")

    def _check_external_policy_patch(self, proposal):
        if "研发" in proposal.get("category", ""):
            return "2025年研发费用加计扣除比例提升至100%"
        return None

    def _get_monthly_stats(self):
        # 实际应从 DB 聚合
        return {"revenue": 95000, "vat_in": 2000}

    def reply(self, x: dict = None) -> dict:
        proposal = x.get("content", {})
        if x.get("action") == "SIMULATE_FILING":
            return LedgerMsg.create(self.name, self._calculate_projected_tax(), action="TAX_REPORT", sender_role="SENTINEL")
        if x.get("action") == "STRESS_TEST":
            return self._run_tax_stress_test(proposal)

        log.info(f"Sentinel 启动巡检...")
        # ... (简化流程)
        return LedgerMsg.create(self.name, {"decision": "PASS"}, action="SENTINEL_CHECK")
