import json
from db_helper import DBHelper
from logger import get_logger

log = get_logger("InteractionHub")

class InteractionHub:
    def __init__(self):
        self.db = DBHelper()
        self.card_version = "v1.2"

    def create_action_card(self, title, content, actions=None, inputs=None, images=None, charts=None, payload=None):
        """
        [Optimization 3] 增强型多模态 ActionCard
        """
        card = {
            "version": self.card_version,
            "header": {"title": title, "style": "primary"},
            "body": {
                "content": content,
                "images": images or [], # 支持 OCR 原始图片
                "charts": charts or []  # 支持利润/偏差图表
            },
            "actions": actions or [],
            "inputs": inputs or [],
            "metadata": payload or {}
        }
        return card

    def push_context_request(self, transaction_id, vendor, amount, trace_id=None):
        """
        [Optimization 3] 主动向老板补充业务背景
        """
        content = f"大哥，这笔来自【{vendor}】的支出 (￥{amount:.2f}) 审计存疑。麻烦补充一下【业务目的】或【招待对象】。"
        
        inputs = [{"id": "biz_purpose", "label": "业务背景", "placeholder": "例：招待某项目重要客户"}]
        actions = [{"label": "提交说明", "value": "SUBMIT_CONTEXT", "style": "primary"}]
        
        card = self.create_action_card(
            title="🔍 业务背景补全",
            content=content,
            actions=actions,
            inputs=inputs,
            payload={"trans_id": transaction_id, "trace_id": trace_id}
        )
        return card

    def push_card(self, transaction_id, proposal_data, trace_id=None, required_role="ADMIN"):
        """
        [Suggestion 3] 推送卡片并注入 RBAC 权限标识
        """
        # 优化点：在推送前强制执行隐私脱敏
        from privacy_guard import PrivacyGuard
        guard = PrivacyGuard(role="GUEST")
        
        safe_data = {}
        for k, v in proposal_data.items():
            safe_data[k] = guard.desensitize(v, context="NOTE") if isinstance(v, str) else v
            
        # 封装为标准化卡片
        actions = [
            {"label": "确认入账", "value": "CONFIRM", "style": "success"},
            {"label": "科目修正", "value": "EDIT", "style": "warning"},
            {"label": "拒绝单据", "value": "REJECT", "style": "danger"}
        ]
        
        card = self.create_action_card(
            title=f"分录审批 - {safe_data.get('vendor', '未知商户')}",
            content=f"金额: {safe_data.get('amount')}\n科目: {safe_data.get('category')}\n原因: {safe_data.get('reason')}",
            actions=actions,
            payload={
                "trans_id": transaction_id, 
                "trace_id": trace_id,
                "required_role": required_role # [Suggestion 3]
            }
        )
        
        log.info(f"推送标准化交互卡片 ({self.card_version}): Transaction={transaction_id} | Role={required_role}")
        return card

    def push_evidence_request(self, transaction_id, vendor, amount, trace_id=None):
        """
        [Optimization 3] 主动向老板索要票据证据 (F4.5)
        """
        content = f"老板，检测到一笔来自【{vendor}】的支出 (￥{amount:.2f})，目前缺少发票或收据证据。请拍照上传以确认为合规支出。"
        
        actions = [
            {"label": "现在拍照/上传", "value": "UPLOAD_REQUEST", "style": "primary"},
            {"label": "稍后处理", "value": "REMIND_LATER", "style": "secondary"}
        ]
        
        card = self.create_action_card(
            title="🔍 补充证据请求",
            content=content,
            actions=actions,
            payload={
                "trans_id": transaction_id,
                "trace_id": trace_id,
                "request_type": "EVIDENCE_MISSING"
            }
        )
        
        log.info(f"发送主动证据索要请求: Transaction={transaction_id}")
        # 在真实场景中，这里会调用 IM 接口发送此 card
        return card

    def render_for_platform(self, card, platform="FEISHU"):
        """
        [Optimization 1] IM 多渠道适配器 (Multi-Channel Adapter)
        将标准 ActionCard 转换为特定 IM 平台的 Payload
        """
        if platform == "FEISHU":
            return {
                "msg_type": "interactive",
                "card": {
                    "header": {
                        "title": {"tag": "plain_text", "content": card['header']['title']},
                        "template": "blue" if card['header']['style'] == "primary" else "red"
                    },
                    "elements": [
                        {"tag": "div", "text": {"tag": "lark_md", "content": card['body']['content']}},
                        {"tag": "action", "actions": [
                            {"tag": "button", "text": {"tag": "plain_text", "content": a['label']}, "value": a['value']}
                            for a in card['actions']
                        ]}
                    ]
                }
            }
        elif platform == "WECHAT_WORK":
            # 模拟企业微信 Markdown 格式
            actions_md = " | ".join([f"[{a['label']}]" for a in card['actions']])
            return {
                "msgtype": "markdown",
                "markdown": {
                    "content": f"## {card['header']['title']}\n{card['body']['content']}\n\n> 操作: {actions_md}"
                }
            }
        return card

    def handle_callback(self, transaction_id, action_value, provided_trace_id, original_trace_id, user_role="GUEST", signature=None, extra_payload=None, timestamp=None):
        """
        处理回调，增加签名校验与手动修正回流 (F3.4.2)
        [Suggestion 2] 安全强化：增加重放攻击防护 (Replay Protection)
        [Suggestion 3] 增加 RBAC 权限校验
        """
        import time
        
        # 1. 重放攻击检查 (5分钟窗口)
        if timestamp:
            current_ts = int(time.time())
            if abs(current_ts - int(timestamp)) > 300:
                log.error(f"回调请求过期 (Timestamp: {timestamp})，拒绝处理以防止重放攻击。")
                return False

        # 获取卡片要求的权限
        required_role = "ADMIN" # 默认
        if extra_payload and 'required_role' in extra_payload:
            required_role = extra_payload['required_role']

        if user_role != required_role and required_role != "GUEST":
            log.error(f"越权操作拦截: 用户角色 {user_role} 试图执行需 {required_role} 权限的任务")
            return False

        if signature:
            # 优化点：校验 HMAC 签名
            import hmac, hashlib
            payload_str = f"{transaction_id}:{action_value}"
            if timestamp: payload_str += f":{timestamp}"
            if extra_payload:
                payload_str += f":{json.dumps(extra_payload, sort_keys=True)}"
                
            # 模拟密钥获取
            secret = "secret_key" 
            expected_sig = hmac.new(secret.encode(), payload_str.encode(), hashlib.sha256).hexdigest()
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

        # [Suggestion 5] 双向反查回路 (OpenManus Ask-Back)
        elif action_value == "PROVIDE_INFO":
            info = extra_payload.get('user_input')
            log.info(f"收到用户补充信息: {info}，正在通知 OpenManus 继续推理...")
            # 这里应触发 OpenManus 恢复挂起的任务，此处仅打日志模拟
            return True
            
        return False
