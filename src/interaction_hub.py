import json
from db_helper import DBHelper
from logger import get_logger

log = get_logger("InteractionHub")

class InteractionHub:
    def __init__(self):
        self.db = DBHelper()

    def push_card(self, transaction_id, proposal_data, trace_id=None):
        # 优化点：在推送前强制执行隐私脱敏
        from privacy_guard import PrivacyGuard
        guard = PrivacyGuard(role="GUEST")
        
        safe_data = {}
        for k, v in proposal_data.items():
            safe_data[k] = guard.desensitize(v, context="NOTE") if isinstance(v, str) else v
            
        log.info(f"推送已脱敏的交互卡片: Transaction={transaction_id}")
        return {"transaction_id": transaction_id, "trace_id": trace_id, "data": safe_data}

    def handle_callback(self, transaction_id, action_value, provided_trace_id, original_trace_id, signature=None, extra_payload=None):
        """
        处理回调，增加签名校验与手动修正回流 (F3.4.2)
        """
        if signature:
            # 优化点：校验 HMAC 签名
            import hmac, hashlib
            payload_str = f"{transaction_id}:{action_value}"
            if extra_payload:
                payload_str += f":{json.dumps(extra_payload, sort_keys=True)}"
                
            expected_sig = hmac.new(b"secret_key", payload_str.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected_sig):
                log.error(f"回调签名错误！可能存在篡改风险。")
                return False

        if provided_trace_id != original_trace_id:
            log.error(f"回调令牌不匹配！")
            return False
            
        # 1. 处理拒绝逻辑
        if action_value == "REJECT":
            with self.db.transaction("IMMEDIATE") as conn:
                conn.execute("UPDATE transactions SET status = 'BLOCKED' WHERE id = ?", (transaction_id,))
            log.warning(f"交易 {transaction_id} 已被老板拒绝。")
            return True
            
        # 2. 处理确认/修正逻辑
        elif action_value == "CONFIRM":
            # 优化点：支持手动修正回流 (HITL 知识沉淀)
            if extra_payload and 'updated_category' in extra_payload:
                new_cat = extra_payload['updated_category']
                vendor = extra_payload.get('vendor', 'Unknown')
                log.info(f"检测到老板手动修正科目: {vendor} -> {new_cat}，启动知识回流...")
                
                from knowledge_bridge import KnowledgeBridge
                KnowledgeBridge().learn_new_rule(vendor, new_cat, source="MANUAL")

            with self.db.transaction("IMMEDIATE") as conn:
                conn.execute("UPDATE transactions SET status = 'POSTED' WHERE id = ?", (transaction_id,))
            log.info(f"交易 {transaction_id} 已确认入账。")
            return True
        
        # 优化点：支持批量消消乐确认 (F3.4.1)
        elif action_value == "BATCH_CONFIRM":
            log.info(f"收到批量消消乐确认指令: {transaction_id}")
            # 此时 transaction_id 可能是一个标识符，真正的 ID 在 extra_payload 中
            if extra_payload and 'item_ids' in extra_payload:
                ids = extra_payload['item_ids']
                with self.db.transaction("IMMEDIATE") as conn:
                    for tid in ids:
                        conn.execute("UPDATE transactions SET status = 'POSTED' WHERE id = ?", (tid,))
                log.info(f"批量确认成功，共处理 {len(ids)} 笔交易。")
                return True
            
        return False
