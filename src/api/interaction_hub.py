import json
import time
import threading
from core.db_helper import DBHelper
from core.db_models import Transaction, SystemEvent
from infra.logger import get_logger
from core.config_manager import ConfigManager
from infra.graceful_exit import should_exit
from sqlalchemy import text, func
from connectors.feishu_connector import FeishuConnector

log = get_logger("InteractionHub")


class InteractionHub:
    def __init__(self):
        self.db = DBHelper()
        self.card_version = "v1.5.0"
        self.im_enabled = ConfigManager.get("im.enabled", False)
        self.feishu = FeishuConnector() if self.im_enabled else None

    def create_action_card(
        self,
        title,
        content,
        actions=None,
        inputs=None,
        images=None,
        charts=None,
        payload=None,
    ):
        card = {
            "version": self.card_version,
            "header": {"title": title, "style": "primary"},
            "body": {
                "content": content,
                "images": images or [],
                "charts": charts or [],
            },
            "actions": actions or [],
            "inputs": inputs or [],
            "metadata": payload or {},
        }
        return card

    def push_context_request(self, transaction_id, vendor, amount, trace_id=None):
        content = f"大哥，这笔来自【{vendor}】的支出 (￥{amount:.2f}) 审计存疑。麻烦补充一下【业务背景】或【招待对象】。"
        inputs = [
            {
                "id": "biz_purpose",
                "label": "业务背景",
                "placeholder": "例：招待某项目重要客户",
            }
        ]
        actions = [{"label": "提交说明", "value": "SUBMIT_CONTEXT", "style": "primary"}]
        card = self.create_action_card(
            "🔍 业务背景补全",
            content,
            actions,
            inputs,
            payload={"trans_id": transaction_id, "trace_id": trace_id},
        )
        self._dispatch_to_im(card)
        return card

    def push_card(
        self, transaction_id, proposal_data, trace_id=None, required_role="ADMIN"
    ):
        from infra.privacy_guard import PrivacyGuard

        guard = PrivacyGuard(role="GUEST")
        safe_data = {
            k: (guard.desensitize(v, context="NOTE") if isinstance(v, str) else v)
            for k, v in proposal_data.items()
        }
        actions = [
            {"label": "确认入账", "value": "CONFIRM", "style": "success"},
            {"label": "科目修正", "value": "EDIT", "style": "warning"},
            {"label": "拒绝单据", "value": "REJECT", "style": "danger"},
        ]
        card = self.create_action_card(
            f"分录审批 - {safe_data.get('vendor', '未知商户')}",
            f"金额: {safe_data.get('amount')}\n科目: {safe_data.get('category')}\n原因: {safe_data.get('reason')}",
            actions,
            payload={
                "trans_id": transaction_id,
                "trace_id": trace_id,
                "required_role": required_role,
            },
        )
        self._dispatch_to_im(card)
        return card

    def push_evidence_request(self, transaction_id, vendor, amount, trace_id=None):
        content = f"老板，检测到一笔来自【{vendor}】的支出 (￥{amount:.2f})，目前缺少发票或收据证据。请拍照上传以确认为合规支出。"
        actions = [
            {"label": "现在拍照/上传", "value": "UPLOAD_REQUEST", "style": "primary"},
            {"label": "稍后处理", "value": "REMIND_LATER", "style": "secondary"},
        ]
        card = self.create_action_card(
            "🔍 补充证据请求",
            content,
            actions,
            payload={
                "trans_id": transaction_id,
                "trace_id": trace_id,
                "request_type": "EVIDENCE_MISSING",
            },
        )
        self._dispatch_to_im(card)
        return card

    def _dispatch_to_im(self, internal_card):
        if not self.im_enabled or not self.feishu:
            return
        feishu_card = self.feishu.transform_internal_to_feishu(internal_card)
        self.feishu.send_card(feishu_card)

    def push_card(
        self, transaction_id, proposal_data, trace_id=None, required_role="ADMIN"
    ):
        from infra.privacy_guard import PrivacyGuard

        guard = PrivacyGuard(role="GUEST")
        safe_data = {
            k: (guard.desensitize(v, context="NOTE") if isinstance(v, str) else v)
            for k, v in proposal_data.items()
        }
        actions = [
            {"label": "确认入账", "value": "CONFIRM", "style": "success"},
            {"label": "科目修正", "value": "EDIT", "style": "warning"},
            {"label": "拒绝单据", "value": "REJECT", "style": "danger"},
        ]
        return self.create_action_card(
            f"分录审批 - {safe_data.get('vendor', '未知商户')}",
            f"金额: {safe_data.get('amount')}\n科目: {safe_data.get('category')}\n原因: {safe_data.get('reason')}",
            actions,
            payload={
                "trans_id": transaction_id,
                "trace_id": trace_id,
                "required_role": required_role,
            },
        )

    def push_evidence_request(self, transaction_id, vendor, amount, trace_id=None):
        content = f"老板，检测到一笔来自【{vendor}】的支出 (￥{amount:.2f})，目前缺少发票或收据证据。请拍照上传以确认为合规支出。"
        actions = [
            {"label": "现在拍照/上传", "value": "UPLOAD_REQUEST", "style": "primary"},
            {"label": "稍后处理", "value": "REMIND_LATER", "style": "secondary"},
        ]
        return self.create_action_card(
            "🔍 补充证据请求",
            content,
            actions,
            payload={
                "trans_id": transaction_id,
                "trace_id": trace_id,
                "request_type": "EVIDENCE_MISSING",
            },
        )

    def handle_callback(
        self,
        transaction_id,
        action_value,
        provided_trace_id,
        original_trace_id,
        user_role="GUEST",
        signature=None,
        extra_payload=None,
        timestamp=None,
    ):
        if provided_trace_id != original_trace_id:
            return False
        if action_value == "REJECT":
            with self.db.transaction() as session:
                session.query(Transaction).filter_by(id=transaction_id).update(
                    {"status": "BLOCKED"}, synchronize_session=False
                )
            return True
        elif action_value == "CONFIRM":
            vendor = "Unknown"
            new_cat = None
            if extra_payload:
                new_cat = extra_payload.get("updated_category")
                vendor = extra_payload.get("vendor", "Unknown")
            if new_cat:
                from core.knowledge_bridge import KnowledgeBridge

                KnowledgeBridge().learn_new_rule(vendor, new_cat, source="MANUAL")
                with self.db.transaction() as session:
                    session.query(Transaction).filter(
                        Transaction.vendor == vendor, Transaction.status == "PENDING"
                    ).update(
                        {"category": new_cat, "status": "PENDING_AUDIT"},
                        synchronize_session=False,
                    )
            with self.db.transaction() as session:
                row = session.query(Transaction).filter_by(id=transaction_id).first()
                if row:
                    self.db.update_trial_balance(row.category, float(row.amount))
                    row.status = "POSTED"
            return True
        return False


class PollingWorker(threading.Thread):
    def __init__(self, hub):
        super().__init__(daemon=True, name="Interaction-Poll")
        self.hub = hub
        self.db = hub.db

    def run(self):
        log.info("InteractionHub 轮询服务启动 (Event-Driven Mode)...")
        last_proactive_check = 0
        while not should_exit():
            try:
                now = time.time()
                # 1. 处理系统事件 (PUSH_CARD, EVIDENCE_REQUEST)
                with self.db.transaction() as session:
                    # 获取最近 30 秒内的未处理事件
                    events_objs = (
                        session.query(SystemEvent)
                        .filter(
                            SystemEvent.event_type.in_(
                                ["PUSH_CARD", "EVIDENCE_REQUEST"]
                            ),
                            SystemEvent.created_at
                            > func.now() - text("interval '30 seconds'"),
                        )
                        .order_by(SystemEvent.created_at.asc())
                        .all()
                    )

                    for event in events_objs:
                        event_data = {
                            "id": event.id,
                            "event_type": event.event_type,
                            "message": event.message,
                            "trace_id": event.trace_id,
                        }
                        self._dispatch_event(event_data)
                        event.event_type = "HANDLED_" + event.event_type

                # 2. 定期执行主动任务扫描
                if now - last_proactive_check > 60:
                    self._check_proactive_tasks()
                    last_proactive_check = now

                time.sleep(5)
            except Exception as e:
                log.error(f"Hub 轮询异常: {e}")
                time.sleep(5)

    def _dispatch_event(self, event):
        etype = event["event_type"]
        try:
            payload = json.loads(event["message"])
            data = payload.get("data", {})

            if etype == "PUSH_CARD":
                self.hub.push_card(
                    data.get("trans_id"), data, trace_id=event["trace_id"]
                )
                log.info(
                    f"【通知发送】已推送审批卡片: {payload.get('type')} | TraceID: {event['trace_id']}"
                )

            elif etype == "EVIDENCE_REQUEST":
                self.hub.push_evidence_request(
                    data.get("trans_id"),
                    data.get("vendor"),
                    data.get("amount"),
                    trace_id=event["trace_id"],
                )
                log.info(
                    f"【通知发送】已推送证据追索: {data.get('vendor')} | TraceID: {event['trace_id']}"
                )

        except Exception as e:
            log.error(f"分发事件失败: {e} | EventID: {event['id']}")

    def _check_proactive_tasks(self):
        try:
            with self.db.transaction() as session:
                # 查找 rejected 1分钟 或 pending 10分钟的任务
                cutoff_rejected = func.now() - text("interval '1 minute'")
                cutoff_pending = func.now() - text("interval '10 minutes'")

                from sqlalchemy import or_, and_

                tasks_objs = (
                    session.query(Transaction)
                    .filter(
                        or_(
                            and_(
                                Transaction.status == "REJECTED",
                                Transaction.created_at < cutoff_rejected,
                            ),
                            and_(
                                Transaction.status == "PENDING",
                                Transaction.created_at < cutoff_pending,
                            ),
                        )
                    )
                    .limit(3)
                    .all()
                )

                for task in tasks_objs:
                    if task.status == "REJECTED":
                        self.hub.push_card(
                            task.id,
                            {
                                "vendor": task.vendor,
                                "amount": task.amount,
                                "category": "待修正",
                                "reason": "审计未通过",
                            },
                            trace_id=task.trace_id,
                        )
                    else:
                        self.hub.push_evidence_request(
                            task.id, task.vendor, task.amount, trace_id=task.trace_id
                        )
        except Exception as e:
            log.error(f"主动任务检查失败: {e}")


if __name__ == "__main__":
    hub = InteractionHub()
    worker = PollingWorker(hub)
    worker.start()
    log.info("InteractionHub 服务已启动...")
    while not should_exit():
        time.sleep(1)
