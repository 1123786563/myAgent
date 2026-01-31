from bus_init import LedgerMsg
from agentscope.agents import AgentBase
from logger import get_logger
from db_helper import DBHelper
import re

log = get_logger("AuditorAgent")

class AuditorAgent(AgentBase):
    def __init__(self, name):
        super().__init__(name=name)
        from config_manager import ConfigManager
        self.db = DBHelper()
        # 预编译科目编码校验正则
        self.category_pattern = re.compile(r'^\d{4}-\d{2}')
        # 优化点：从配置中心读取审计阈值 (Suggestion 2)
        self.auto_approve_threshold = ConfigManager.get("audit.auto_approve_threshold", 0.95)
        self.force_manual_amount = ConfigManager.get("audit.force_manual_amount", 100000)
        log.info(f"AuditorAgent 初始化完成: 大额风控线={self.force_manual_amount}")

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

    def reply(self, x: dict = None) -> dict:
        proposal = x.get("content", {})
        category = proposal.get("category", "")
        confidence = proposal.get("confidence", 0)
        amount = float(x.get("amount", 0))
        vendor = x.get("vendor", "Unknown")
        trace_id = x.get("trace_id", "Unknown")
        
        # 优化点：检索供应商当前的审计状态
        audit_info = self._get_vendor_audit_info(vendor)
        audit_status = audit_info.get("audit_status", "GRAY")
        
        # 优化点：使用 FTS5 语义模糊匹配提升历史偏好检索
        history_category = self._get_historical_preference_fts(vendor)
        
        reasons = []
        is_rejected = False
        risk_score = 1.0 - confidence # 风险分与置信度反向相关

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
        
        if is_rejected or risk_score > 0.15: # 风险分阈值
            decision = "REJECT"
            # 优化点：引入异构逻辑补救 (Suggestion 1: L2 Heterogeneous Audit)
            if 0.15 < risk_score < 0.4 and not is_rejected:
                log.info(f"触发异构逻辑补救: {trace_id}")
                if self._trigger_l2_heterogeneous_audit(proposal):
                    decision = "APPROVED"
                    final_reason = "L1 存疑，但 L2 异构审计(Heterogeneous Consensus)通过"
                    risk_score = 0.1
                else:
                    final_reason = "L1 存疑且 L2 异构审计未通过"
            else:
                final_reason = " | ".join(reasons) if reasons else "综合置信度不足"
        
        # 5. 更新知识反馈回路
        self._update_audit_result(vendor, is_success=(decision == "APPROVED"))

        result = {
            "decision": decision,
            "reason": final_reason,
            "audit_score": 1.0 - risk_score,
            "risk_score": min(1.0, risk_score),
            "is_risky": is_rejected or audit_status == "GRAY"
        }
        
        # 优化点：日志输出带上 trace_id 供 TraceFilter 捕获
        log.info(f"审计决策: {decision} | Vendor: {vendor} | Status: {audit_status} | Reason: {final_reason}", extra={'trace_id': trace_id})
        return LedgerMsg.create(self.name, result, action="AUDIT_RESULT", trace_id=trace_id)

    def _get_vendor_audit_info(self, vendor):
        """获取供应商的审计元数据"""
        try:
            with self.db.transaction("DEFERRED") as conn:
                sql = "SELECT audit_status, audit_level, consecutive_success FROM knowledge_base WHERE entity_name = ?"
                row = conn.execute(sql, (vendor,)).fetchone()
                return dict(row) if row else {"audit_status": "GRAY", "audit_level": "NORMAL", "consecutive_success": 0}
        except:
            return {"audit_status": "GRAY", "audit_level": "NORMAL", "consecutive_success": 0}

    def _trigger_l2_heterogeneous_audit(self, proposal):
        """
        [Suggestion 1] 实现 L2 异构审计
        实际场景中此处会调用另一个 LLM 节点进行反向博弈
        """
        # 模拟：如果科目中包含“招待”且金额 < 1000，则 L2 倾向于放行
        category = proposal.get("category", "")
        amount = float(proposal.get("amount", 0))
        if "招待" in category and amount < 1000:
            return True
        return self._heterogeneous_double_check(proposal)

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
