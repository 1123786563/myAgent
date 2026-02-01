from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy import text, func, desc
from core.db_helper import DBHelper
from core.db_models import SystemEvent, Transaction
from api.interaction_hub import InteractionHub
from infra.logger import get_logger
import json
from datetime import datetime, timedelta

router = APIRouter()
log = get_logger("UIRoutes")
hub = InteractionHub()


@router.get("/dashboard/metrics")
async def get_dashboard_metrics():
    """Get dashboard key metrics"""
    db = DBHelper()
    try:
        stats = db.get_ledger_stats()  # list of dicts: status, count, total_amount
        monthly = db.get_monthly_stats()  # revenue, total_expense

        # Process stats
        pending = next(
            (item["count"] for item in stats if item["status"] == "PENDING"), 0
        )
        matched = next(
            (item["count"] for item in stats if item["status"] == "MATCHED"), 0
        )

        # Calculate health score
        total = sum(item["count"] for item in stats)
        rejected = next(
            (item["count"] for item in stats if item["status"] == "REJECTED"), 0
        )
        health_score = 100
        if total > 0:
            health_score = 100 - int((rejected / total) * 100)
        health_score = max(0, min(100, health_score))

        balance = monthly.get("revenue", 0) - monthly.get("total_expense", 0)

        return {
            "metrics": {
                "balance": balance,
                "pending_vouchers": pending,
                "matched_invoices": matched,
                "health_score": health_score,
            }
        }
    except Exception as e:
        log.error(f"Error fetching dashboard metrics: {e}")
        return {
            "metrics": {
                "balance": 0,
                "pending_vouchers": 0,
                "matched_invoices": 0,
                "health_score": 0,
            }
        }


@router.get("/dashboard/chart")
async def get_dashboard_chart():
    """Get dashboard trend chart data"""
    db = DBHelper()
    try:
        with db.transaction() as session:
            # Query last 14 days transaction amount
            end_date = datetime.now()
            start_date = end_date - timedelta(days=14)

            results = (
                session.query(
                    func.date(Transaction.created_at).label("date"),
                    func.sum(Transaction.amount).label("amount"),
                )
                .filter(Transaction.created_at >= start_date)
                .group_by(func.date(Transaction.created_at))
                .order_by(func.date(Transaction.created_at))
                .all()
            )

            data = []
            for r in results:
                data.append(
                    {
                        "date": str(r.date),
                        "value": float(r.amount or 0),
                        "category": "交易额",
                    }
                )
            
            # If no data, return empty list or mock for demo if DB is empty?
            # Let's return actual data.
            return {"data": data}
    except Exception as e:
        log.error(f"Error fetching dashboard chart: {e}")
        return {"data": []}


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
