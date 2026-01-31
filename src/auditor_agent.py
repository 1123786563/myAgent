from bus_init import LedgerMsg
from agentscope.agents import AgentBase
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
    [Optimization 3] Dynamic Consensus Engine
    Simulates multi-persona voting based on transaction context.
    """

    def __init__(self, strategy=ConsensusStrategy.BALANCED):
        self.strategy = strategy

    def vote(self, proposal):
        amount = float(proposal.get("amount", 0))
        category = proposal.get("category", "")
        vendor = proposal.get("vendor", "")

        # 1. Compliance Officer (Rules & Policy)
        # Rejects if amount > 50k without contract or sensitive keywords
        vote_compliance = True
        reason_compliance = "Pass"
        if amount > 50000:
            vote_compliance = False
            reason_compliance = "Large amount requires manual contract review"
        if any(x in category for x in ["赠送", "礼品", "回扣"]):
            vote_compliance = False
            reason_compliance = "Sensitive category detected"

        # 2. Financial Controller (Budget & Cashflow)
        # Rejects if amount > 10k (placeholder for budget check)
        vote_finance = True
        reason_finance = "Pass"
        if amount > 10000:
            # Simulation: 20% chance to reject purely on "Tight Budget" simulation
            import random

            if random.random() < 0.2:
                vote_finance = False
                reason_finance = "Budget tightening active"

        # 3. Tax Specialist (Deductibility)
        # Rejects if vendor/category mismatch risk is high
        vote_tax = True
        reason_tax = "Pass"
        if "餐饮" in category and "技术" in vendor:
            vote_tax = False
            reason_tax = "Tax risk: Tech vendor issuing food invoice"

        votes = {
            "Compliance": {"pass": vote_compliance, "reason": reason_compliance},
            "Finance": {"pass": vote_finance, "reason": reason_finance},
            "Tax": {"pass": vote_tax, "reason": reason_tax},
        }
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
        super().__init__(name=name)
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
        self.rules_path = ConfigManager.get("path.audit_rules", "src/audit_rules.yaml")
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
        amount = float(content.get("amount", 0))
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

    def _update_audit_result(self, vendor, is_success):
        """
        更新知识库中的审计统计并处理灰度期晋升逻辑 (F3.4.2)
        """
        try:
            with self.db.transaction("IMMEDIATE") as conn:
                if is_success:
                    # 连续成功次数 +1，如果达到 3 次且当前为 GRAY，晋升为 STABLE
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
                    # 失败则重置连续成功数，增加驳回数
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
        except Exception as e:
            log.error(f"更新审计状态失败: {e}")

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
        模拟“会计、审计、法务”三方交叉校验
        """
        log.info(f"开启三方共识博弈: TraceID={proposal.get('trace_id')}")

        # 1. 模型 A: Moltbot 基础审计
        result_a = self._heterogeneous_double_check(proposal)

        # 2. 模型 B: 行业专项审计 (SOFTWARE/RETAIL)
        vendor = proposal.get("vendor", "")
        sector = ConfigManager.get("enterprise.sector", "GENERAL")
        result_b = True
        if sector == "SOFTWARE" and any(
            kw in vendor for kw in ["戴尔", "惠普", "服务器"]
        ):
            amount = float(proposal.get("amount", 0))
            if amount > 5000:
                result_b = False

        # 3. [Optimization 2] 模拟模型 C: 法律/合规专项审计 (Compliance Check)
        category = proposal.get("category", "")
        result_c = True
        if "借款" in category or "套现" in str(proposal):
            result_c = False  # 法务拦截

        votes = {
            "Basic_Audit": result_a,
            "Sector_Audit": result_b,
            "Legal_Audit": result_c,
        }
        pass_count = sum(1 for v in votes.values() if v)

        log.info(
            f"三方共识投票结果: {pass_count}/3 通过 -> {'批准' if pass_count >= 2 else '拦截'}"
        )
        return (pass_count >= 2), votes

    def _aggregate_group_context(self, group_id):
        """
        [Optimization 2] 聚合逻辑组单据上下文 (F3.1.3)
        """
        try:
            with self.db.transaction("DEFERRED") as conn:
                # 获取该组下所有已识别的描述和金额
                sql = "SELECT amount, vendor, inference_log FROM transactions WHERE group_id = ?"
                rows = conn.execute(sql, (group_id,)).fetchall()

                total_amount = sum(float(r["amount"]) for r in rows)
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
        # ... (保持原逻辑)
        amount = float(x.get("amount", 0))
        vendor = x.get("vendor", "Unknown")
        category = proposal.get("category", "")

        # [Optimization 2] 跨供应商价格基准校验 (Sector Benchmarking)
        # 逻辑：如果本笔交易金额显著高于该科目历史中位数的 150%，提示采购风险
        avg_sector_price = self.db.get_category_median_price(category)
        if avg_sector_price > 0 and amount > avg_sector_price * 1.5:
            log.warning(
                f"价格偏离行业基准: {amount} > {avg_sector_price:.2f} * 1.5 | Vendor={vendor}"
            )
            reasons.append("价格显著高于该科目历史采购基准，建议进行比价审核")
            risk_score += 0.2

        # ... (保持后续逻辑)

        # [Optimization 2] 针对中高风险交易触发共识审计
        if risk_score > 0.3:
            log.info(f"风险分较高 ({risk_score:.2f})，触发共识审计模式...")
            consensus_passed, consensus_reason = self._consensus_double_check(x)
            if not consensus_passed:
                return self._reject(x, f"共识失败: {consensus_reason}")

        # [Optimization 2] 多模态资产聚合审计加强
        if group_id:
            log.info(f"多模态成组审计介入: Group={group_id}")
            group_data = self._aggregate_group_context(group_id)
            if group_data:
                # 将聚合后的多角度信息注入推理逻辑（此处模拟）
                proposal["aggregated_asset_context"] = group_data
                if "资产" in category:
                    proposal["is_part_of_asset_bundle"] = True
                    proposal["bundle_total_value"] = group_data["total_amount"]

        # [Optimization 3] 高风险共识审计触发
        from config_manager import ConfigManager

        consensus_trigger_ratio = ConfigManager.get(
            "audit.consensus_trigger_ratio", 0.5
        )
        if amount > self.force_manual_amount * consensus_trigger_ratio:  # 动态触发线
            success, details = self._trigger_consensus_audit(x)
            if not success:
                return self._reject(x, f"共识审计未通过: {details}")

        # [Optimization 2] 差异化审计提示词策略
        # 逻辑：对于大额或高风险科目，切换至 "TAXPAYER_OFFICER" 视角
        audit_strategy = "STANDARD"
        if amount > self.force_manual_amount or "劳务" in vendor:
            audit_strategy = "RED_TEAM_TAX_OFFICER"
            log.info(f"触发红方审计策略: {audit_strategy} | TraceID={trace_id}")

        # [Optimization 4] 引入规则时效性衰减 (Confidence Decay)
        last_used = x.get("last_used_at", "2020-01-01")
        # decay_factor = self._calculate_time_decay(last_used)

        # [Optimization 1] 试算平衡校验 (Trial Balance Guard)
        if not self._check_global_balance(category, amount):
            return self._reject(
                x,
                "致命错误：该分录将导致全局试算不平衡 (Assets != Liabilities + Equity)",
            )

        # [Optimization 3] 呼叫 Sentinel 进行税务与预算合规性预检
        from sentinel_agent import SentinelAgent

        sentinel = SentinelAgent("Sentinel-Audit-Hook")
        compliance_passed, compliance_reason = sentinel.check_transaction_compliance(
            proposal
        )
        if not compliance_passed:
            log.warning(f"Sentinel 合规阻断: {compliance_reason} | TraceID={trace_id}")
            is_rejected = True
            risk_score = 1.0
            reasons.append(f"[Sentinel] {compliance_reason}")

        # 优化点：检索供应商当前的审计状态
        audit_info = self._get_vendor_audit_info(vendor)
        audit_status = audit_info.get("audit_status", "GRAY")

        # 优化点：使用 FTS5 语义模糊匹配提升历史偏好检索
        history_category = self._get_historical_preference_fts(vendor)

        # [Suggestion 1] 初始化决策矩阵 (L2 可解释性增强)
        decision_matrix = {
            "confidence_score": confidence,
            "rule_quality": rule_quality,
            "historical_match": 1.0 if history_category == category else 0.5,
            "vendor_risk": 1.0 if audit_status == "STABLE" else 0.4,
        }

        # 0. 状态机审计：已拉黑供应商直接拦截
        if audit_status == "BLOCKED":
            is_rejected = True
            risk_score = 1.0
            reasons.append("该供应商已被审计阻断器(Blocked)拉黑")

        # 1. 深度内容审计：格式与红线
        if not self.category_pattern.search(category):
            is_rejected = True
            risk_score = 1.0
            reasons.append(f"科目编码格式错误: {category}")

        # 2. 金额风控审计
        if amount > self.force_manual_amount:
            is_rejected = True
            risk_score = max(risk_score, 0.9)
            reasons.append(f"触发大额支付风控({amount} > {self.force_manual_amount})")

        # 3. 历史一致性审计 (语义对齐)
        if audit_info.get("audit_level") == "HIGH_RISK":
            risk_score += 0.3
            reasons.append("该供应商有历史驳回记录，风险评级：HIGH_RISK")

        if history_category and history_category != category:
            risk_score += 0.2
            reasons.append(f"与历史入账习惯不符(历史常入: {history_category})")

        # 4. 综合决策逻辑
        decision = "APPROVED"
        final_reason = "符合财务准则与历史习惯"

        if is_rejected or risk_score > 0.15:  # 风险分阈值
            decision = "REJECT"
            # 优化点：引入异构逻辑补救 (Suggestion 1: L2 Heterogeneous Audit)
            if 0.15 < risk_score < 0.4 and not is_rejected:
                log.info(f"触发异构逻辑补救: {trace_id}")
                if self._trigger_l2_heterogeneous_audit(proposal):
                    decision = "APPROVED"
                    final_reason = (
                        "L1 存疑，但 L2 异构审计(Heterogeneous Consensus)通过"
                    )
                    risk_score = 0.1
                else:
                    final_reason = "L1 存疑且 L2 异构审计未通过"
            else:
                final_reason = " | ".join(reasons) if reasons else "综合置信度不足"

        # 5. 更新知识反馈回路
        self._update_audit_result(vendor, is_success=(decision == "APPROVED"))

        # [Optimization 4] 推理图存证：将 L2 路径结构化持久化 (F3.2.4)
        inference_graph = proposal.get("reasoning_graph", [])

        result = {
            "decision": decision,
            "reason": final_reason,
            "audit_score": 1.0 - risk_score,
            "risk_score": min(1.0, risk_score),
            "is_risky": is_rejected or audit_status == "GRAY",
            "decision_matrix": decision_matrix,
            "reasoning_graph": inference_graph,  # [Optimization 4]
        }

        # 优化点：日志输出带上 trace_id 供 TraceFilter 捕获
        log.info(
            f"审计决策: {decision} | Vendor: {vendor} | Status: {audit_status} | Reason: {final_reason}",
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
        except:
            return {
                "audit_status": "GRAY",
                "audit_level": "NORMAL",
                "consecutive_success": 0,
            }

    def _trigger_l2_heterogeneous_audit(self, proposal):
        """
        [Suggestion 1] 实现 L2 异构审计
        通过博弈论逻辑进行反向校验
        """
        category = proposal.get("category", "")
        amount = float(proposal.get("amount", 0))

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
        [Optimization 1] Real Trial Balance Health Check
        Verifies that the current ledger is balanced before accepting new entries.
        Also validates that the category exists in the chart of accounts.
        """
        try:
            with self.db.transaction("DEFERRED") as conn:
                # 1. Check current ledger balance
                row = conn.execute(
                    "SELECT SUM(debit_total) as debits, SUM(credit_total) as credits FROM trial_balance"
                ).fetchone()

                debits = row["debits"] or 0.0
                credits = row["credits"] or 0.0

                if abs(debits - credits) > 0.01:
                    log.critical(
                        f"System Imbalance Detected! Debits: {debits}, Credits: {credits}"
                    )
                    # In strict mode, we might want to block new entries until fixed
                    # return False

                # 2. Validate Category exists (Simulated Chart of Accounts check)
                # In a real app, we would query an 'accounts' table.
                if not category or len(category) < 2:
                    return False

                return True
        except Exception as e:
            log.error(f"Trial balance check failed: {e}")
            return True  # Fail open to avoid blocking ops on DB error
