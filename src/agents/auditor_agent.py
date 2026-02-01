import re
import os
import json
from decimal import Decimal
from core.bus_init import LedgerMsg
from agentscope.agent import AgentBase
from infra.logger import get_logger
from core.db_helper import DBHelper
from core.config_manager import ConfigManager
from utils.decimal_utils import to_decimal
from agents.auditor_consensus import ConsensusEngine, ConsensusStrategy
from agents.auditor_risk import AuditorRiskAssessment

log = get_logger("AuditorAgent")

class AuditorAgent(AgentBase):
    def __init__(self, name):
        super().__init__()
        self.name = name
        self.db = DBHelper()
        self.category_pattern = re.compile(r"^\d{4}-\d{2}")
        self.auto_approve_threshold = ConfigManager.get("audit.auto_approve_threshold", 0.95)
        self.force_manual_amount = ConfigManager.get("audit.force_manual_amount", 100000)
        self.consensus_engine = ConsensusEngine(strategy=ConsensusStrategy.BALANCED)
        self.risk_assessor = AuditorRiskAssessment(self.db, self.category_pattern, self.force_manual_amount)
        self.rules_path = ConfigManager.get("path.audit_rules", "src/core/audit_rules.yaml")
        self._load_audit_rules()

    def _load_audit_rules(self):
        try:
            import yaml
            if os.path.exists(self.rules_path):
                with open(self.rules_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    self.audit_rules = data.get("rules", [])
            else: self.audit_rules = []
        except: self.audit_rules = []

    def reply(self, x: dict = None) -> dict:
        proposal = x.get("content", {})
        amount = to_decimal(x.get("amount", 0))
        vendor = x.get("vendor", "Unknown")
        category = proposal.get("category", "")
        trace_id = x.get("trace_id")
        group_id = x.get("group_id")
        
        confidence = proposal.get("confidence", 0.5)
        risk_score = 0.0
        reasons = []
        is_rejected = False

        is_valid, fmt_reason = self.risk_assessor.assess_category_format(category)
        if not is_valid:
            is_rejected = True
            reasons.append(fmt_reason)

        p_risk, p_reasons = self.risk_assessor.assess_price_benchmark_risk(category, amount, vendor)
        risk_score += p_risk
        reasons.extend(p_reasons)

        audit_info = self._get_vendor_audit_info(vendor)
        history_cat = self._get_historical_preference_fts(vendor)
        v_risk, v_reasons, v_blocked = self.risk_assessor.assess_vendor_risk(vendor, category, audit_info, history_cat)
        risk_score += v_risk
        reasons.extend(v_reasons)
        if v_blocked: is_rejected = True

        a_risk, a_reasons, _ = self.risk_assessor.assess_amount_risk(amount)
        risk_score += a_risk
        reasons.extend(a_reasons)

        c_passed, c_reasons, c_risk = self.risk_assessor.perform_compliance_check(x)
        if not c_passed:
            is_rejected = True
            reasons.extend(c_reasons)
            risk_score += c_risk

        if (risk_score > 0.3) or (amount > self.force_manual_amount * ConfigManager.get_float("audit.consensus_trigger_ratio", 0.5)):
            success, _ = self.consensus_engine.vote(x), self.consensus_engine.decide(self.consensus_engine.vote(x))
            if not success: return self._reject(x, "共识审计未通过")

        if group_id:
            group_data = self._aggregate_group_context(group_id)
            if group_data: proposal["aggregated_asset_context"] = group_data

        if not self._check_global_balance(category, amount):
            return self._reject(x, "致命错误：该分录将导致全局试算不平衡")

        decision, final_reason, final_risk = self._make_final_decision(is_rejected, risk_score, reasons, x, trace_id)
        self._update_audit_result(vendor, is_success=(decision == "APPROVED"), risk_score=final_risk, trace_id=trace_id)

        result = {
            "decision": decision, "reason": final_reason,
            "audit_score": 1.0 - final_risk, "risk_score": min(1.0, final_risk),
            "is_risky": is_rejected or audit_info.get("audit_status") == "GRAY"
        }
        return LedgerMsg.create(self.name, result, action="AUDIT_RESULT", trace_id=trace_id)

    def _get_vendor_audit_info(self, vendor):
        try:
            with self.db.transaction("DEFERRED") as conn:
                sql = "SELECT audit_status, audit_level, consecutive_success FROM knowledge_base WHERE entity_name = ?"
                row = conn.execute(sql, (vendor,)).fetchone()
                return dict(row) if row else {"audit_status": "GRAY", "audit_level": "NORMAL", "consecutive_success": 0}
        except: return {"audit_status": "GRAY", "audit_level": "NORMAL", "consecutive_success": 0}

    def _get_historical_preference_fts(self, vendor):
        try:
            with self.db.transaction("DEFERRED") as conn:
                sql = "SELECT t.category FROM transactions t JOIN knowledge_base k ON t.vendor = k.entity_name WHERE k.id IN (SELECT rowid FROM kb_fts WHERE entity_name MATCH ?) AND t.status = 'AUDITED' GROUP BY t.category ORDER BY COUNT(*) DESC LIMIT 1"
                row = conn.execute(sql, (f"{vendor}*",)).fetchone()
                return row["category"] if row else None
        except: return None

    def _aggregate_group_context(self, group_id):
        try:
            with self.db.transaction("DEFERRED") as conn:
                rows = conn.execute("SELECT amount, vendor, inference_log FROM transactions WHERE group_id = ?", (group_id,)).fetchall()
                return {"total_amount": sum(to_decimal(r["amount"]) for r in rows), "vendors": list(set(r["vendor"] for r in rows if r["vendor"]))}
        except: return None

    def _check_global_balance(self, category, amount):
        try:
            with self.db.transaction("DEFERRED") as conn:
                row = conn.execute("SELECT SUM(debit_total) as debits, SUM(credit_total) as credits FROM trial_balance").fetchone()
                if row and abs((row["debits"] or 0) - (row["credits"] or 0)) > 0.01:
                    log.critical("系统试算不平衡警告！")
                return bool(category and len(category) >= 2)
        except: return True

    def _make_final_decision(self, is_rejected, risk_score, reasons, proposal, trace_id):
        decision = "APPROVED"
        final_reason = "符合财务准则与历史习惯"
        reject_threshold = ConfigManager.get_float("threshold.risk_score_reject", 0.15)
        if is_rejected or risk_score > reject_threshold:
            decision = "REJECT"
            final_reason = " | ".join(reasons) if reasons else "综合置信度不足"
        return decision, final_reason, risk_score

    def _update_audit_result(self, vendor, is_success, risk_score=0.0, trace_id=None):
        try:
            with self.db.transaction("IMMEDIATE") as conn:
                if is_success:
                    sql = "UPDATE knowledge_base SET hit_count = hit_count + 1, consecutive_success = consecutive_success + 1, audit_status = CASE WHEN audit_status = 'GRAY' AND consecutive_success >= 2 THEN 'STABLE' ELSE audit_status END, updated_at = CURRENT_TIMESTAMP WHERE entity_name = ?"
                else:
                    sql = "UPDATE knowledge_base SET reject_count = reject_count + 1, consecutive_success = 0, audit_status = CASE WHEN reject_count >= 3 THEN 'BLOCKED' ELSE audit_status END, audit_level = 'HIGH_RISK', updated_at = CURRENT_TIMESTAMP WHERE entity_name = ?"
                conn.execute(sql, (vendor,))
        except: pass

    def _reject(self, x, reason):
        return LedgerMsg.create(self.name, {"decision": "REJECT", "reason": reason, "audit_score": 0}, action="AUDIT_RESULT", trace_id=x.get("trace_id"), sender_role="AUDITOR")
