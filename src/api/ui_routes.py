from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy import text, func, desc
from core.db_helper import DBHelper
from core.db_models import SystemEvent, Transaction
from api.interaction_hub import InteractionHub
from infra.logger import get_logger
import json

router = APIRouter()
log = get_logger("UIRoutes")
hub = InteractionHub()


@router.get("/cards/pending")
async def get_pending_cards():
    """Get all pending interaction cards"""
    db = DBHelper()
    cards = []

    try:
        with db.transaction() as session:
            # Query unhandled PUSH_CARD and EVIDENCE_REQUEST events
            # We assume 'HANDLED_' prefix means handled
            events = (
                session.query(SystemEvent)
                .filter(
                    SystemEvent.event_type.in_(["PUSH_CARD", "EVIDENCE_REQUEST"]),
                    # In a real system we'd filter out handled ones, but here we just check message content or status
                    # For now, let's fetch recent 50
                )
                .order_by(desc(SystemEvent.created_at))
                .limit(50)
                .all()
            )

            for event in events:
                try:
                    payload = json.loads(event.message)
                    # Enrich with event metadata
                    payload["event_id"] = event.id
                    payload["event_type"] = event.event_type
                    payload["trace_id"] = event.trace_id
                    payload["created_at"] = event.created_at.isoformat()

                    # Check if associated transaction is already processed
                    trans_id = payload.get("data", {}).get("trans_id")
                    if trans_id:
                        trans = session.query(Transaction).get(trans_id)
                        if trans and trans.status not in [
                            "PENDING",
                            "PENDING_AUDIT",
                            "REJECTED",
                        ]:
                            payload["status"] = "COMPLETED"
                        else:
                            payload["status"] = "PENDING"

                    cards.append(payload)
                except Exception as e:
                    log.error(f"Failed to parse event {event.id}: {e}")

    except Exception as e:
        log.error(f"Error fetching cards: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return {"data": cards}


@router.post("/cards/{event_id}/action")
async def handle_card_action(
    event_id: int, action: dict, background_tasks: BackgroundTasks
):
    """
    Handle user action on a card
    action body: { "action_value": "CONFIRM", "payload": {...} }
    """
    db = DBHelper()
    try:
        with db.transaction() as session:
            event = session.query(SystemEvent).get(event_id)
            if not event:
                raise HTTPException(status_code=404, detail="Event not found")

            event_payload = json.loads(event.message)
            data = event_payload.get("data", {})
            trans_id = data.get("trans_id")
            trace_id = event.trace_id

            action_value = action.get("action_value")
            extra_payload = action.get("payload", {})

            # Delegate to InteractionHub logic
            # run in background to avoid blocking
            background_tasks.add_task(
                hub.handle_callback,
                transaction_id=trans_id,
                action_value=action_value,
                provided_trace_id=trace_id,
                original_trace_id=trace_id,
                user_role="ADMIN",  # Assume admin for UI
                extra_payload=extra_payload,
            )

            # Mark event as handled (optional, or just append log)
            event.event_type = f"HANDLED_{event.event_type}"

        return {"status": "success", "message": "Action submitted"}

    except Exception as e:
        log.error(f"Error handling action: {e}")
        raise HTTPException(status_code=500, detail=str(e))
