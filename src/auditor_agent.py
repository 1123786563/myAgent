from bus_init import LedgerMsg
from agentscope.agents import AgentBase
from logger import get_logger
from db_helper import DBHelper
import re

log = get_logger("AuditorAgent")

class AuditorAgent(AgentBase):
    def __init__(self, name):
        super().__init__(name=name)
        self.db = DBHelper()
        # 预编译科目编码校验正则
        self.category_pattern = re.compile(r'^\d{4}-\d{2}')
        # 审计阈值配置
        self.auto_approve_threshold = 0.95
        self.force_manual_amount = 100000

    def _heterogeneous_double_check(self, proposal):
        """
        模拟异构审计逻辑：使用不同的判别维度
        """
        # 维度 A: 行业常识校验 (Amount vs Category)
        amount = float(proposal.get("amount", 0))
        category = proposal.get("category", "")
        if "差旅" in category and amount > 5000:
            return False
        # 维度 B: 供应商信用评分 (假设外部调取)
        return True

    def _update_risk_knowledge(self, vendor):
        """更新知识库中的风险等级"""
        sql = "INSERT INTO knowledge_base (entity_name, audit_level) VALUES (?, 'HIGH_RISK') ON CONFLICT(entity_name) DO UPDATE SET audit_level='HIGH_RISK'"
        try:
            with self.db.transaction() as conn:
                conn.execute(sql, (vendor,))
        except:
            pass

    def reply(self, x: dict = None) -> dict:
        proposal = x.get("content", {})
        category = proposal.get("category", "")
        confidence = proposal.get("confidence", 0)
        amount = float(x.get("amount", 0))
        vendor = x.get("vendor", "Unknown")
        trace_id = x.get("trace_id", "Unknown")
        
        # 优化点：使用 FTS5 语义模糊匹配提升历史偏好检索
        history_category = self._get_historical_preference_fts(vendor)
        
        reasons = []
        is_rejected = False
        risk_score = 1.0 - confidence # 风险分与置信度反向相关

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
        if history_category == "HIGH_RISK_FLAG":
            is_rejected = True
            risk_score = 1.0
            reasons.append("该供应商已被标记为高风险，需人工介入")
        elif history_category and history_category != category:
            risk_score += 0.2
            reasons.append(f"与历史入账习惯不符(历史常入: {history_category})")

        # 4. 综合决策逻辑
        decision = "APPROVED"
        final_reason = "符合财务准则与历史习惯"
        
        if is_rejected or risk_score > 0.15: # 风险分阈值
            decision = "REJECT"
            # 优化点：引入异构逻辑补救 (L2 尝试)
            if 0.15 < risk_score < 0.4 and not is_rejected:
                log.info(f"触发异构逻辑补救: {trace_id}")
                if self._heterogeneous_double_check(proposal):
                    decision = "APPROVED"
                    final_reason = "L1 存疑，但 L2 异构审计通过"
                    risk_score = 0.1
                else:
                    final_reason = "L1 存疑且 L2 异构审计未通过"
            else:
                final_reason = " | ".join(reasons) if reasons else "综合置信度不足"
                
            if decision == "REJECT":
                # 优化点：如果被驳回，记录风险反馈到知识库
                if is_rejected or risk_score > 0.4:
                    self._update_risk_knowledge(vendor)
                
                # 优化点：打通知识自进化负反馈回路 (F3.4.2)
                matched_rule = proposal.get("matched_rule")
                if matched_rule and matched_rule != "None":
                    from knowledge_bridge import KnowledgeBridge
                    KnowledgeBridge().record_rule_rejection(matched_rule)

        result = {
            "decision": decision,
            "reason": final_reason,
            "audit_score": 1.0 - risk_score,
            "risk_score": min(1.0, risk_score),
            "is_risky": is_rejected
        }
        
        # 优化点：日志输出带上 trace_id 供 TraceFilter 捕获
        log.info(f"审计决策: {decision} | Vendor: {vendor} | Reason: {final_reason}", extra={'trace_id': trace_id})
        return LedgerMsg.create(self.name, result, action="AUDIT_RESULT", trace_id=trace_id)

    def _get_historical_preference_fts(self, vendor):
        """
        利用 FTS5 进行供应商模糊搜索并检查偏好
        """
        try:
            with self.db.transaction("DEFERRED") as conn:
                # 1. 优先检查精确匹配的高风险标志
                check_sql = "SELECT audit_level FROM knowledge_base WHERE entity_name = ?"
                kb_row = conn.execute(check_sql, (vendor,)).fetchone()
                if kb_row and kb_row['audit_level'] == 'HIGH_RISK':
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
                return row['category'] if row else None
        except Exception:
            return None

    def _reject(self, x, reason):
        result = {"decision": "REJECT", "reason": reason, "audit_score": 0}
        return LedgerMsg.create(self.name, result, action="AUDIT_RESULT", trace_id=x.get("trace_id"))
