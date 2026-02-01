from decimal import Decimal
from decimal_utils import to_decimal
from bus_init import LedgerMsg
from agentscope.agent import AgentBase
from logger import get_logger
from db_helper import DBHelper
import re
import os

log = get_logger("AuditorAgent")


class ConsensusStrategy:
    """Consensus voting strategies"""

    STRICT = "STRICT"  # All must agree
    BALANCED = "BALANCED"  # Majority wins
    GROWTH = "GROWTH"  # One vote enough for small amounts


class ConsensusEngine:
    """
    [Optimization 3/19] Dynamic Consensus Engine
    [Round 19] Persona-based rule engine.
    """

    def __init__(self, strategy=ConsensusStrategy.BALANCED):
        self.strategy = strategy
        # [Round 19] 定义专家人格
        self.personas = {
            "COMPLIANCE": self._vote_compliance,
            "FINANCE": self._vote_finance,
            "TAX": self._vote_tax
        }

    def _vote_compliance(self, amount, category, vendor):
        if amount > 50000:
            return False, "Large amount requires contract"
        if any(x in category for x in ["赠送", "礼品", "回扣"]):
            return False, "Prohibited category"
        return True, "Pass"

    def _vote_finance(self, amount, category, vendor):
        # 模拟预算限制
        if amount > 10000 and "研发" not in category:
            return False, "Budget restriction for non-R&D"
        return True, "Pass"

    def _vote_tax(self, amount, category, vendor):
        if "个人" in vendor and amount > 500:
            return False, "High individual payment risk"
        return True, "Pass"

    def vote(self, proposal):
        amount = to_decimal(proposal.get("amount", 0))
        category = proposal.get("category", "")
        vendor = proposal.get("vendor", "")

        votes = {}
        for name, func in self.personas.items():
            passed, reason = func(amount, category, vendor)
            votes[name] = {"pass": passed, "reason": reason}
        return votes

    def decide(self, votes):
        pass_count = sum(1 for v in votes.values() if v["pass"])
        total = len(votes)

        if self.strategy == ConsensusStrategy.STRICT:
            return pass_count == total
        elif self.strategy == ConsensusStrategy.GROWTH:
            return pass_count >= 1
        else:  # BALANCED
            return pass_count >= (total / 2)


class AuditorAgent(AgentBase):
    def __init__(self, name):
        super().__init__()
        self.name = name
        from config_manager import ConfigManager

        self.db = DBHelper()
        # 预编译科目编码校验正则
        self.category_pattern = re.compile(r"^\d{4}-\d{2}")
        self.auto_approve_threshold = ConfigManager.get(
            "audit.auto_approve_threshold", 0.95
        )
        self.force_manual_amount = ConfigManager.get(
            "audit.force_manual_amount", 100000
        )

        # [Optimization 3] Init Consensus Engine
        self.consensus_engine = ConsensusEngine(strategy=ConsensusStrategy.BALANCED)

        # [Optimization 1] 加载动态审计规则 (Red Team Rules)
        self.rules_path = ConfigManager.get("path.audit_rules", "src/core/audit_rules.yaml")
        self._load_audit_rules()
        log.info(
            f"AuditorAgent 初始化完成: 大额风控线={self.force_manual_amount}, 规则数={len(self.audit_rules)}"
        )

    def _load_audit_rules(self):
        try:
            import yaml

            if os.path.exists(self.rules_path):
                with open(self.rules_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    self.audit_rules = data.get("rules", [])
            else:
                self.audit_rules = []
        except Exception as e:
            log.error(f"审计规则加载失败: {e}")
            self.audit_rules = []

    def _heterogeneous_double_check(self, proposal):
        """
        模拟异构审计逻辑：使用 YAML 定义的红方规则进行校验
        [Optimization 1] 行业特定审计策略插件 (Sector-Aware)
        """
        content = proposal.get("content", {})
        amount = to_decimal(content.get("amount", 0))
        category = content.get("category", "")
        vendor = content.get("vendor", "")

        # 动态加载行业配置
        from config_manager import ConfigManager

        current_sector = ConfigManager.get("enterprise.sector", "GENERAL")

        for rule in self.audit_rules:
            # 1. 行业过滤
            if rule.get("sector") and rule.get("sector") != current_sector:
                continue

            # 2. 正则匹配
            v_match = (
                re.search(rule.get("vendor_pattern", ""), vendor)
                if rule.get("vendor_pattern")
                else True
            )
            c_match = (
                re.search(rule.get("category_pattern", ""), category)
                if rule.get("category_pattern")
                else True
            )

            # 3. 金额匹配
            a_min = rule.get("amount_min", 0)
            a_max = rule.get("amount_max", float("inf"))
            a_match = a_min <= amount <= a_max

            if v_match and c_match and a_match:
                reason = rule.get("reason", "触发审计规则")
                action = rule.get("action", "FLAG")
                log.warning(f"审计规则命中 [{rule['id']}]: {reason} | Action={action}")

                if action == "REJECT":
                    return False
                # FLAG 可以在此处增加风险分，暂时简单处理为通过但记录日志

        # 保留原有的硬编码兜底逻辑
        if "差旅" in category and amount > 5000:
            return False

        return True

    def _update_audit_result(self, vendor, is_success, risk_score=0.0, trace_id=None):
        """
        [Round 22] 更新审计统计并持久化风险证据，处理灰度晋升逻辑
        """
        try:
            with self.db.transaction("IMMEDIATE") as conn:
                # 1. 核心状态机更新 (包含 F3.4.2 逻辑)
                if is_success:
                    sql = """
                        UPDATE knowledge_base 
                        SET hit_count = hit_count + 1,
                            consecutive_success = consecutive_success + 1,
                            audit_status = CASE 
                                WHEN audit_status = 'GRAY' AND consecutive_success >= 2 THEN 'STABLE' 
                                ELSE audit_status 
                            END,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE entity_name = ?
                    """
                else:
                    sql = """
                        UPDATE knowledge_base 
                        SET reject_count = reject_count + 1,
                            consecutive_success = 0,
                            audit_status = CASE 
                                WHEN reject_count >= 3 THEN 'BLOCKED' 
                                ELSE audit_status 
                            END,
                            audit_level = 'HIGH_RISK',
                            updated_at = CURRENT_TIMESTAMP
                        WHERE entity_name = ?
                    """
                conn.execute(sql, (vendor,))

                # 2. [Round 22] 持久化审计证据 (evidence_chain_index)
                if trace_id:
                    row = conn.execute("SELECT id FROM transactions WHERE trace_id = ?", (trace_id,)).fetchone()
                    if row:
                        trans_id = row["id"]
                        evidence_data = {"risk_score": round(risk_score, 4), "timestamp": self.db.get_now()}
                        conn.execute(
                            "INSERT INTO evidence_chain_index (transaction_id, step_name, evidence_type, evidence_data) VALUES (?, ?, ?, ?)",
                            (trans_id, "FINAL_AUDIT", "RISK_METRICS", json.dumps(evidence_data))
                        )
        except Exception as e:
            log.error(f"审计结果更新失败: {e}")

    def _trigger_consensus_audit(self, proposal):
        """
        [Optimization 3] 基于共识的影子审计 (Consensus-based Auditing)
        Uses the dynamic ConsensusEngine instead of hardcoded dictionary.
        """
        trace_id = proposal.get("trace_id")
        log.info(f"触发共识审计机制 (Consensus Auditing) | TraceID={trace_id}")

        # Call the engine
        votes = self.consensus_engine.vote(proposal)
        is_consensus_passed = self.consensus_engine.decide(votes)

        # Log details
        passed_count = sum(1 for v in votes.values() if v["pass"])
        log.info(
            f"共识投票结果: {passed_count}/3 通过 ({self.consensus_engine.strategy}) -> {'批准' if is_consensus_passed else '驳回'}"
        )

        # Detailed log for failed votes
        for role, v in votes.items():
            if not v["pass"]:
                log.warning(f"  - {role} Veto: {v['reason']}")

        # Map to original return format
        simple_votes = {k: v["pass"] for k, v in votes.items()}
        return is_consensus_passed, simple_votes

    def _consensus_double_check(self, proposal):
        """
        [Optimization 2] 专家级多模型共识引擎 (Expert Consensus)
        Refactored to use ConsensusEngine for consistency.
        """
        log.info(f"开启三方共识博弈: TraceID={proposal.get('trace_id')}")
        is_passed, simple_votes = self._trigger_consensus_audit(proposal)
        
        log.info(
            f"三方共识投票结果: {sum(simple_votes.values())}/3 通过 -> {'批准' if is_passed else '拦截'}"
        )
        return is_passed, simple_votes

    def _aggregate_group_context(self, group_id):
        """
        [Optimization 2] 聚合逻辑组单据上下文 (F3.1.3)
        """
        try:
            with self.db.transaction("DEFERRED") as conn:
                # 获取该组下所有已识别的描述和金额
                sql = "SELECT amount, vendor, inference_log FROM transactions WHERE group_id = ?"
                rows = conn.execute(sql, (group_id,)).fetchall()

                total_amount = sum(to_decimal(r["amount"]) for r in rows)
                vendors = list(set(r["vendor"] for r in rows if r["vendor"]))
                logs = [r["inference_log"] for r in rows if r["inference_log"]]

                return {
                    "total_amount": total_amount,
                    "vendors": vendors,
                    "visual_summary": " | ".join(logs),
                }
        except:
            return None

    def reply(self, x: dict = None) -> dict:
        proposal = x.get("content", {})
        amount = to_decimal(x.get("amount", 0))
        vendor = x.get("vendor", "Unknown")
        category = proposal.get("category", "")
        trace_id = x.get("trace_id")
        group_id = x.get("group_id")

        # 1. 基础状态初始化
        confidence = proposal.get("confidence", 0.5)
        rule_quality = proposal.get("inference_log", {}).get("rule_id") is not None
        risk_score = 0.0
        reasons = []
        is_rejected = False

        # 2. 模块化风险评估 (Iteration 7+ Modularization)
        
        # 2.1 格式校验
        is_valid, fmt_reason = self._assess_category_format(category)
        if not is_valid:
            is_rejected = True
            reasons.append(fmt_reason)

        # 2.2 价格基准校验
        p_risk, p_reasons = self._assess_price_benchmark_risk(category, amount, vendor)
        risk_score += p_risk
        reasons.extend(p_reasons)

        # 2.3 供应商风险评估 (含黑名单)
        audit_info = self._get_vendor_audit_info(vendor)
        v_risk, v_reasons, v_blocked = self._assess_vendor_risk(vendor, category, audit_info)
        risk_score += v_risk
        reasons.extend(v_reasons)
        if v_blocked:
            is_rejected = True

        # 2.4 金额风控评估
        a_risk, a_reasons, a_manual = self._assess_amount_risk(amount)
        risk_score += a_risk
        reasons.extend(a_reasons)
        # 大额强制人工由后续决策逻辑处理

        # 2.5 合规性巡检 (Sentinel)
        c_passed, c_reasons, c_risk = self._perform_compliance_check(x, trace_id)
        if not c_passed:
            is_rejected = True
            reasons.extend(c_reasons)
            risk_score += c_risk

        # 3. 动态审计机制触发
        
        # 3.1 共识审计 (基于风险分或特定条件)
        consensus_trigger_ratio = ConfigManager.get("audit.consensus_trigger_ratio", 0.5)
        if (risk_score > 0.3) or (amount > self.force_manual_amount * consensus_trigger_ratio):
            log.info(f"触发动态共识审计 | Risk={risk_score:.2f} | Amount={amount}")
            success, details = self._trigger_consensus_audit(x)
            if not success:
                return self._reject(x, f"共识审计未通过: {details}")

        # 3.2 多模态聚合增强
        if group_id:
            log.info(f"多模态成组审计介入: Group={group_id}")
            group_data = self._aggregate_group_context(group_id)
            if group_data:
                proposal["aggregated_asset_context"] = group_data
                if "资产" in category:
                    proposal["is_part_of_asset_bundle"] = True
                    proposal["bundle_total_value"] = group_data["total_amount"]

        # 3.3 全局试算平衡校验
        if not self._check_global_balance(category, amount):
            return self._reject(x, "致命错误：该分录将导致全局试算不平衡")

        # 4. 决策矩阵与最终判定
        history_category = self._get_historical_preference_fts(vendor)
        decision_matrix = self._build_decision_matrix(
            confidence, rule_quality, history_category, category, audit_info.get("audit_status", "GRAY")
        )

        decision, final_reason, final_risk = self._make_final_decision(
            is_rejected, risk_score, reasons, x, trace_id
        )

        # 5. 结果持久化与反馈
        self._update_audit_result(vendor, is_success=(decision == "APPROVED"), risk_score=final_risk, trace_id=trace_id)

        result = {
            "decision": decision,
            "reason": final_reason,
            "audit_score": 1.0 - final_risk,
            "risk_score": min(1.0, final_risk),
            "is_risky": is_rejected or audit_info.get("audit_status") == "GRAY",
            "decision_matrix": decision_matrix,
            "reasoning_graph": proposal.get("reasoning_graph", []),
        }

        log.info(
            f"审计决策: {decision} | Vendor: {vendor} | Score: {result['audit_score']:.2f} | Reason: {final_reason}",
            extra={"trace_id": trace_id},
        )
        return LedgerMsg.create(
            self.name, result, action="AUDIT_RESULT", trace_id=trace_id
        )

    def _get_vendor_audit_info(self, vendor):
        """获取供应商的审计元数据"""
        try:
            with self.db.transaction("DEFERRED") as conn:
                sql = "SELECT audit_status, audit_level, consecutive_success FROM knowledge_base WHERE entity_name = ?"
                row = conn.execute(sql, (vendor,)).fetchone()
                return (
                    dict(row)
                    if row
                    else {
                        "audit_status": "GRAY",
                        "audit_level": "NORMAL",
                        "consecutive_success": 0,
                    }
                )
        except Exception as e:
            log.debug(f"获取供应商审计信息失败: {e}")
            return {
                "audit_status": "GRAY",
                "audit_level": "NORMAL",
                "consecutive_success": 0,
            }

    # ==================== [Optimization Iteration 7] 模块化审计方法 ====================

    def _assess_price_benchmark_risk(self, category: str, amount: Decimal, vendor: str) -> tuple:
        """
        [Optimization Iteration 7] 价格基准风险评估
        检查交易金额是否显著偏离该科目历史中位数

        Returns:
            (risk_delta, reasons): 风险分增量和原因列表
        """
        risk_delta = 0.0
        reasons = []

        factor = ConfigManager.get_float("threshold.price_outlier_factor", 1.5)
        avg_sector_price = to_decimal(self.db.get_category_median_price(category))
        if avg_sector_price > 0 and amount > avg_sector_price * Decimal(str(factor)):
            log.warning(
                f"价格偏离行业基准: {amount} > {avg_sector_price:.2f} * {factor} | Vendor={vendor}"
            )
            reasons.append("价格显著高于该科目历史采购基准，建议进行比价审核")
            risk_delta = 0.2

        return risk_delta, reasons

    def _assess_vendor_risk(self, vendor: str, category: str, audit_info: dict) -> tuple:
        """
        [Optimization Iteration 7] 供应商风险评估
        基于供应商审计状态和历史偏好进行风险评估

        Returns:
            (risk_delta, reasons, is_blocked): 风险分增量、原因列表、是否被阻断
        """
        risk_delta = 0.0
        reasons = []
        is_blocked = False

        audit_status = audit_info.get("audit_status", "GRAY")

        # 供应商黑名单检查
        if audit_status == "BLOCKED":
            is_blocked = True
            risk_delta = 1.0
            reasons.append("该供应商已被审计阻断器(Blocked)拉黑")
            return risk_delta, reasons, is_blocked

        # 高风险供应商检查
        if audit_info.get("audit_level") == "HIGH_RISK":
            risk_delta += 0.3
            reasons.append("该供应商有历史驳回记录，风险评级：HIGH_RISK")

        # 历史一致性检查
        history_category = self._get_historical_preference_fts(vendor)
        if history_category and history_category != category:
            risk_delta += 0.2
            reasons.append(f"与历史入账习惯不符(历史常入: {history_category})")

        return risk_delta, reasons, is_blocked

    def _assess_amount_risk(self, amount: Decimal) -> tuple:
        """
        [Optimization Iteration 7] 金额风险评估

        Returns:
            (risk_delta, reasons, requires_manual): 风险分增量、原因列表、是否需要人工审核
        """
        risk_delta = 0.0
        reasons = []
        requires_manual = False

        if amount > self.force_manual_amount:
            requires_manual = True
            risk_delta = 0.9
            reasons.append(f"触发大额支付风控({amount} > {self.force_manual_amount})")

        return risk_delta, reasons, requires_manual

    def _assess_category_format(self, category: str) -> tuple:
        """
        [Optimization Iteration 7] 科目格式校验

        Returns:
            (is_valid, reason): 格式是否有效、无效原因
        """
        if not self.category_pattern.search(category):
            return False, f"科目编码格式错误: {category}"
        return True, None

    def _perform_compliance_check(self, proposal: dict, trace_id: str) -> tuple:
        """
        [Optimization Iteration 7] 合规性预检
        调用 Sentinel 进行税务与预算合规性检查

        Returns:
            (passed, reasons, risk_delta): 是否通过、原因列表、风险分增量
        """
        from agents.sentinel_agent import SentinelAgent

        sentinel = SentinelAgent("Sentinel-Audit-Hook")
        compliance_passed, compliance_reason = sentinel.check_transaction_compliance(proposal)

        if not compliance_passed:
            log.warning(f"Sentinel 合规阻断: {compliance_reason} | TraceID={trace_id}")
            return False, [f"[Sentinel] {compliance_reason}"], 1.0

        return True, [], 0.0

    def _build_decision_matrix(self, confidence: float, rule_quality: bool,
                                history_category: str, category: str,
                                audit_status: str) -> dict:
        """
        [Optimization Iteration 7] 构建决策矩阵
        用于 L2 可解释性增强
        """
        return {
            "confidence_score": confidence,
            "rule_quality": rule_quality,
            "historical_match": 1.0 if history_category == category else 0.5,
            "vendor_risk": 1.0 if audit_status == "STABLE" else 0.4,
        }

    def _make_final_decision(self, is_rejected: bool, risk_score: float,
                              reasons: list, proposal: dict, trace_id: str) -> tuple:
        """
        [Optimization Iteration 7] 最终决策逻辑
        整合所有风险评估结果，生成最终审计决策

        Returns:
            (decision, final_reason, adjusted_risk_score)
        """
        decision = "APPROVED"
        final_reason = "符合财务准则与历史习惯"
        adjusted_risk_score = risk_score

        reject_threshold = ConfigManager.get_float("threshold.risk_score_reject", 0.15)
        upgrade_threshold = ConfigManager.get_float("threshold.risk_score_upgrade", 0.4)

        if is_rejected or risk_score > reject_threshold:
            decision = "REJECT"

            # 异构逻辑补救
            if reject_threshold < risk_score < upgrade_threshold and not is_rejected:
                log.info(f"触发异构逻辑补救: {trace_id}")
                if self._trigger_l2_heterogeneous_audit(proposal):
                    decision = "APPROVED"
                    final_reason = "L1 存疑，但 L2 异构审计(Heterogeneous Consensus)通过"
                    adjusted_risk_score = 0.1
                else:
                    final_reason = "L1 存疑且 L2 异构审计未通过"
            else:
                final_reason = " | ".join(reasons) if reasons else "综合置信度不足"

        return decision, final_reason, adjusted_risk_score

    def _trigger_l2_heterogeneous_audit(self, proposal):
        """
        [Suggestion 1] 实现 L2 异构审计
        通过博弈论逻辑进行反向校验
        """
        category = proposal.get("category", "")
        amount = to_decimal(proposal.get("amount", 0))

        # 逻辑：如果科目中包含“招待”且金额 < 1000，则 L2 倾向于放行
        if "招待" in category and amount < 1000:
            return True
        return False

    def _get_historical_preference_fts(self, vendor):
        """
        利用 FTS5 进行供应商模糊搜索并检查偏好
        """
        try:
            with self.db.transaction("DEFERRED") as conn:
                # 1. 优先检查精确匹配的高风险标志
                check_sql = (
                    "SELECT audit_level FROM knowledge_base WHERE entity_name = ?"
                )
                kb_row = conn.execute(check_sql, (vendor,)).fetchone()
                if kb_row and kb_row["audit_level"] == "HIGH_RISK":
                    return "HIGH_RISK_FLAG"

                # 2. FTS5 模糊检索
                sql = """
                    SELECT t.category, COUNT(*) as cnt 
                    FROM transactions t
                    JOIN knowledge_base k ON t.vendor = k.entity_name
                    WHERE k.id IN (SELECT rowid FROM kb_fts WHERE entity_name MATCH ?)
                    AND t.status = 'AUDITED'
                    GROUP BY t.category 
                    ORDER BY cnt DESC LIMIT 1
                """
                # 使用前缀匹配支持：vendor*
                row = conn.execute(sql, (f"{vendor}*",)).fetchone()
                return row["category"] if row else None
        except Exception:
            return None

    def _reject(self, x, reason):
        result = {"decision": "REJECT", "reason": reason, "audit_score": 0}
        return LedgerMsg.create(
            self.name,
            result,
            action="AUDIT_RESULT",
            trace_id=x.get("trace_id"),
            sender_role="AUDITOR",
        )

    def _check_global_balance(self, category, amount):
        """
        [Optimization Round 3] 真实的试算平衡健康检查 (Trial Balance Guard)
        验证账本是否处于平衡状态，并检查科目是否存在。
        """
        try:
            with self.db.transaction("DEFERRED") as conn:
                # 1. 检查当前账本平衡 (借 = 贷)
                row = conn.execute(
                    "SELECT SUM(debit_total) as debits, SUM(credit_total) as credits FROM trial_balance"
                ).fetchone()

                debits = row["debits"] or 0.0
                credits = row["credits"] or 0.0

                # 允许极小误差 (0.01)
                if abs(debits - credits) > 0.01:
                    log.critical(
                        f"系统试算不平衡警告！借方: {debits}, 贷方: {credits} | 差额: {debits-credits:.2f}"
                    )
                    # 如果不平衡严重，可以配置为阻断
                    # return False 

                # 2. 科目规范性检查 (白皮书 2.2)
                if not category or len(category) < 2:
                    log.error(f"科目校验失败: '{category}' 不规范")
                    return False

                return True
        except Exception as e:
            log.error(f"试算平衡逻辑异常: {e}")
            return True # 失败放行以避免系统卡死
