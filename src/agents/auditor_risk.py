from decimal import Decimal
from core.config_manager import ConfigManager
from utils.decimal_utils import to_decimal
from infra.logger import get_logger

log = get_logger("AuditorRiskAssessment")

class AuditorRiskAssessment:
    """
    [Optimization Iteration 7] 模块化审计风险评估
    """
    def __init__(self, db, category_pattern, force_manual_amount):
        self.db = db
        self.category_pattern = category_pattern
        self.force_manual_amount = force_manual_amount

    def assess_price_benchmark_risk(self, category: str, amount: Decimal, vendor: str) -> tuple:
        risk_delta = 0.0
        reasons = []
        factor = ConfigManager.get_float("threshold.price_outlier_factor", 1.5)
        avg_sector_price = to_decimal(self.db.get_category_median_price(category))
        if avg_sector_price > 0 and amount > avg_sector_price * Decimal(str(factor)):
            reasons.append("价格显著高于该科目历史采购基准，建议进行比价审核")
            risk_delta = 0.2
        return risk_delta, reasons

    def assess_vendor_risk(self, vendor: str, category: str, audit_info: dict, historical_category: str) -> tuple:
        risk_delta = 0.0
        reasons = []
        is_blocked = False
        audit_status = audit_info.get("audit_status", "GRAY")
        if audit_status == "BLOCKED":
            return 1.0, ["该供应商已被审计阻断器(Blocked)拉黑"], True
        if audit_info.get("audit_level") == "HIGH_RISK":
            risk_delta += 0.3
            reasons.append("该供应商有历史驳回记录，风险评级：HIGH_RISK")
        if historical_category and historical_category != category:
            risk_delta += 0.2
            reasons.append(f"与历史入账习惯不符(历史常入: {historical_category})")
        return risk_delta, reasons, is_blocked

    def assess_amount_risk(self, amount: Decimal) -> tuple:
        if amount > self.force_manual_amount:
            return 0.9, [f"触发大额支付风控({amount} > {self.force_manual_amount})"], True
        return 0.0, [], False

    def assess_category_format(self, category: str) -> tuple:
        if not self.category_pattern.search(category):
            return False, f"科目编码格式错误: {category}"
        return True, None

    def perform_compliance_check(self, proposal: dict) -> tuple:
        from agents.sentinel_agent import SentinelAgent
        sentinel = SentinelAgent("Sentinel-Audit-Hook")
        compliance_passed, compliance_reason = sentinel.check_transaction_compliance(proposal)
        if not compliance_passed:
            return False, [f"[Sentinel] {compliance_reason}"], 1.0
        return True, [], 0.0
