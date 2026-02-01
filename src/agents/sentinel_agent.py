from bus_init import LedgerMsg
from agentscope.agent import AgentBase
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
        super().__init__()
        self.name = name
        from config_manager import ConfigManager

        self.db = DBHelper()
        # [Suggestion 1] 加载动态阈值
        self.taxpayer_type = ConfigManager.get("tax.taxpayer_type", "SMALL_SCALE")
        self.industry_tax_burden = ConfigManager.get("tax.target_burden", 0.03)
        self.free_limit = ConfigManager.get("tax.free_limit_monthly", 100000)
        self.compliance_redline = ConfigManager.get("tax.compliance_redline", 50000)
        log.info(
            f"SentinelAgent 初始化: 性质={self.taxpayer_type} | 免税额度={self.free_limit}"
        )

    def _check_business_relevance(self, vendor, category):
        """增强的供应商与业务匹配校验"""
        suspicious_pairs = [
            ("餐饮", "办公用品"),
            ("加油站", "差旅费-打车"),
            ("娱乐", "研发支出"),
            ("劳务", "固定资产"),
        ]
        for v_kw, c_kw in suspicious_pairs:
            if v_kw in vendor and c_kw in category:
                return False
        return True

    def _analyze_vendor_price_clustering(self, vendor, category, current_price):
        try:
            # [Optimization 4] Enhanced clustering with Time-Decay Weighting
            sql = """
                SELECT amount, created_at FROM transactions 
                WHERE vendor = ? AND category = ? AND status = 'AUDITED'
                ORDER BY created_at DESC LIMIT 20
            """
            with self.db.transaction("DEFERRED") as conn:
                rows = conn.execute(sql, (vendor, category)).fetchall()

            if len(rows) < 3:
                return True, 0

            import datetime
            import time
            import statistics

            # Parse data points
            data_points = []
            now_ts = time.time()

            for r in rows:
                try:
                    dt = datetime.datetime.strptime(
                        r["created_at"], "%Y-%m-%d %H:%M:%S"
                    )
                    ts = time.mktime(dt.timetuple())
                    data_points.append({"amount": float(r["amount"]), "ts": ts})
                except:
                    continue

            if not data_points:
                return True, 0

            # Calculate Weighted Mean
            # Formula: Weight = 1 / (1 + days_ago) -> Recent prices have higher weight
            total_weight = 0.0
            weighted_sum = 0.0

            for p in data_points:
                days_ago = (now_ts - p["ts"]) / 86400.0
                weight = 1.0 / (1.0 + max(0, days_ago))
                weighted_sum += p["amount"] * weight
                total_weight += weight

            weighted_mean = weighted_sum / total_weight if total_weight > 0 else 0

            # Calculate dynamic threshold based on historical volatility (CV)
            prices = [p["amount"] for p in data_points]
            std_dev = statistics.stdev(prices) if len(prices) > 1 else 0
            cv = std_dev / (weighted_mean + 1e-9)

            # Threshold relaxes if history is volatile
            dynamic_threshold = 0.15 + (cv * 0.5)

            # Deviation check
            deviation = abs(current_price - weighted_mean) / (weighted_mean + 1e-9)

            if deviation > dynamic_threshold:
                log.warning(
                    f"Vendor Price Anomaly: {vendor} | Curr: {current_price} vs WeightedMean: {weighted_mean:.2f} | Dev: {deviation:.1%} > {dynamic_threshold:.1%}"
                )
                return False, deviation

            return True, deviation
        except Exception as e:
            log.error(f"Price analysis failed: {e}")
            return True, 0

    def _calculate_projected_tax(self):
        """
        [Optimization 3] 税务筹划预警逻辑 (Proactive Tax Advisor)
        识别起征点风险并主动推送策略卡片 (F3.3.2)
        """
        stats = self._get_monthly_stats()
        revenue = stats.get("revenue", 0)
        vat_in_actual = stats.get("vat_in", 0)

        # 预估销项税 (Output VAT)
        vat_out_est = revenue * (0.13 if self.taxpayer_type == "GENERAL" else 0.03)

        # [Optimization 3] 策略建议逻辑
        strategy_tips = []
        limit = self.free_limit
        if self.taxpayer_type == "SMALL_SCALE":
            if limit * 0.85 < revenue < limit:
                msg = f"【筹划预警】当前营收 ￥{revenue:,.2f} 已逼近月度免税红线 (￥{limit:,.2f})。建议控制月底开票节奏，或提前确认合规进项。"
                strategy_tips.append(
                    {"title": "月度免税节奏控制", "tip": msg, "action": "ALERT"}
                )
            elif revenue >= limit:
                msg = "本月营收已超免税额度。建议增加合规成本票采集，最大化企业所得税税前扣除。"
                strategy_tips.append(
                    {"title": "进项票据追索建议", "tip": msg, "action": "OPTIMIZE"}
                )

        return {
            "projected_vat": round(vat_out_est - vat_in_actual, 2),
            "strategies": strategy_tips,
            "status": "ADVISORY" if strategy_tips else "NORMAL",
        }

    def _check_budget_compliance(self, dept_name, amount):
        """
        [Optimization 3] 预算红线主动管控 (F3.3.3)
        """
        try:
            with self.db.transaction("DEFERRED") as conn:
                row = conn.execute(
                    "SELECT monthly_limit, current_spent FROM dept_budgets WHERE dept_name = ?",
                    (dept_name,),
                ).fetchone()
                if not row:
                    return True  # 未设预算不拦截

                limit = float(row["monthly_limit"])
                spent = float(row["current_spent"])
                remaining = limit - spent

                if amount > remaining:
                    log.critical(
                        f"预算熔断：{dept_name} 余额 ￥{remaining:.2f} 不足支付 ￥{amount:.2f}！"
                    )
                    return False
                elif (remaining - amount) / limit < 0.15:
                    log.warning(f"预算预警：{dept_name} 支出后余额将低于 15% 红线。")
            return True
        except:
            return True

    def _run_tax_stress_test(self, proposal):
        """
        [Optimization 5] 增强型税务沙箱模拟 (Tax Sandbox)
        """
        sim_spending = float(proposal.get("simulated_spending", 0))
        stats = self._get_monthly_stats()

        # 1. 从数据库加载最新的动态税率
        vat_rate_general = 0.13
        try:
            with self.db.transaction("DEFERRED") as conn:
                row = conn.execute(
                    "SELECT policy_value FROM tax_policies WHERE policy_key = 'vat_rate_general'"
                ).fetchone()
                if row:
                    vat_rate_general = row["policy_value"]
        except:
            pass

        # 2. 计算当前与模拟后的税负
        current_vat_out = stats["revenue"] * vat_rate_general
        current_vat_in = stats.get("vat_in", 0)
        current_payable = max(0, current_vat_out - current_vat_in)

        # 模拟新增进项
        new_vat_in = current_vat_in + (sim_spending * vat_rate_general)
        simulated_payable = max(0, current_vat_out - new_vat_in)

        tax_saving = current_payable - simulated_payable

        result = {
            "strategy": "TAX_SAVING_SIMULATION",
            "current_payable": round(current_payable, 2),
            "simulated_payable": round(simulated_payable, 2),
            "saving": round(tax_saving, 2),
            "recommendation": "建议立即执行" if tax_saving > 1000 else "一般建议",
            "policy_used": f"VAT_RATE_{vat_rate_general * 100}%",
        }
        return LedgerMsg.create(
            self.name, result, action="STRESS_TEST_RESULT", sender_role="SENTINEL"
        )

    def _check_external_policy_patch(self, proposal):
        if "研发" in proposal.get("category", ""):
            return "2025年研发费用加计扣除比例提升至100%"
        return None

    def _get_monthly_stats(self):
        """
        [Optimization 3] 获取本月经营数据聚合 (Real DB Data)
        """
        return self.db.get_monthly_stats()

    def check_transaction_compliance(self, proposal):
        """
        [Optimization 3] 公共合规性检查接口 (供 Auditor 调用)
        返回: (bool passed, str reason)
        """
        vendor = proposal.get("vendor", "")
        category = proposal.get("category", "")
        amount = float(proposal.get("amount", 0))

        # 1. 业务相关性检查
        if not self._check_business_relevance(vendor, category):
            return False, f"业务相关性存疑: 供应商[{vendor}]与科目[{category}]不匹配"

        # 2. 预算检查 (如果能提取出部门)
        # 简单逻辑：假设 tag 中有 department
        tags = proposal.get("tags", [])
        dept = next((t["value"] for t in tags if t["key"] == "department"), None)
        if dept:
            if not self._check_budget_compliance(dept, amount):
                return False, f"预算熔断: 部门[{dept}]余额不足"

        # 3. 价格离群检查
        is_normal, deviation = self._analyze_vendor_price_clustering(
            vendor, category, amount
        )
        if not is_normal:
            return False, f"价格异常: 偏离历史中位数 {deviation:.1%}"

        return True, "Compliance Check Passed"

    def reply(self, x: dict = None) -> dict:
        proposal = x.get("content", {})
        if x.get("action") == "SIMULATE_FILING":
            return LedgerMsg.create(
                self.name,
                self._calculate_projected_tax(),
                action="TAX_REPORT",
                sender_role="SENTINEL",
            )
        if x.get("action") == "STRESS_TEST":
            return self._run_tax_stress_test(proposal)

        log.info(f"Sentinel 启动巡检...")
        # ... (简化流程)
        return LedgerMsg.create(
            self.name, {"decision": "PASS"}, action="SENTINEL_CHECK"
        )
