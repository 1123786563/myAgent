import json
from api.interaction_hub import InteractionHub
from infra.trace_context import TraceContext
from infra.logger import get_logger

log = get_logger("AsyncTaskProcessor")

class AsyncTaskProcessor:
    @staticmethod
    def process_webhook_action(trans_id: int, action_val: str, trace_id: str, user_role: str = "ADMIN"):
        with TraceContext.start_trace(trace_id):
            with TraceContext.start_span("webhook_action_processing", {"trans_id": trans_id, "action": action_val}):
                try:
                    hub = InteractionHub()
                    if hub.handle_callback(transaction_id=trans_id, action_value=action_val, provided_trace_id=trace_id, original_trace_id=trace_id, user_role=user_role):
                        log.info(f"Webhook processed: trans_id={trans_id}, action={action_val}", extra={"trace_id": trace_id})
                    else:
                        log.warning(f"Webhook failed: trans_id={trans_id}", extra={"trace_id": trace_id})
                except Exception as e:
                    log.error(f"Webhook error: {e}", extra={"trace_id": trace_id})
