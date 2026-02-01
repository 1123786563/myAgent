from fastapi import (
    FastAPI,
    HTTPException,
    Request,
    BackgroundTasks,
    Header,
    status,
    Depends,
)
from fastapi.security import APIKeyHeader
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, Dict, Any
import uvicorn
import os
import json
import hashlib
from datetime import datetime
from infra.logger import get_logger
from core.db_helper import DBHelper
from core.db_models import Transaction, SysStatus
from core.config_manager import ConfigManager
from infra.trace_context import TraceContext
from api.api_models import APIResponse, HealthResponse, ErrorResponse, WebhookPayload
from api.api_tasks import AsyncTaskProcessor
from api.api_dashboard import render_dashboard
from auth.routes.auth_routes import router as auth_router
from auth.routes.user_routes import router as user_router
from fastapi.staticfiles import StaticFiles
from auth.routes.role_routes import router as role_router
from api.ui_routes import router as ui_router
from accounting.accounting_routes import router as accounting_router
from accounting.reports_routes import router as reports_router
from accounting.reconciliation_routes import router as reconciliation_router
from accounting.workflow_routes import router as workflow_router
from invoice.invoice_routes import router as invoice_router
from auth.middleware.rate_limit_middleware import RateLimitMiddleware
from auth.middleware.audit_middleware import AuditMiddleware
from sqlalchemy import text, func

log = get_logger("APIServer")
app = FastAPI(title="LedgerAlpha API", version="v2.0")

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=ConfigManager.get("api.cors_origins", ["*"]),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 审计中间件 (在限流之前，记录所有重要操作)
app.add_middleware(AuditMiddleware)

# 限流中间件
app.add_middleware(RateLimitMiddleware)

# 注册认证路由
app.include_router(auth_router, prefix="/api/v1")
app.include_router(user_router, prefix="/api/v1")
app.include_router(role_router, prefix="/api/v1")
app.include_router(ui_router, prefix="/api/v1/ui", tags=["ui"])

# 注册会计模块路由
app.include_router(accounting_router, prefix="/api/v1")
app.include_router(reports_router, prefix="/api/v1")
app.include_router(invoice_router, prefix="/api/v1")
app.include_router(reconciliation_router, prefix="/api/v1")
app.include_router(workflow_router, prefix="/api/v1")

# Mount Static UI
os.makedirs("src/web/static", exist_ok=True)
app.mount("/ui", StaticFiles(directory="src/web/static", html=True), name="static")

# 保留旧的 API Key 认证 (向后兼容，后续废弃)
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


async def get_api_key(api_key: str = Depends(api_key_header)):
    if api_key != ConfigManager.get("api.admin_key", "ledger-secret-2025"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API Key"
        )
    return api_key


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            code=exc.status_code, msg=exc.detail, trace_id=TraceContext.get_trace_id()
        ).model_dump(),
    )


@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    trace_id = request.headers.get("X-Trace-ID") or TraceContext._generate_trace_id()
    with TraceContext.start_trace(trace_id):
        response = await call_next(request)
        response.headers["X-Trace-ID"] = trace_id
        return response


_server_start_time = datetime.now()


@app.get("/health", response_model=HealthResponse)
async def health_check():
    db = DBHelper()
    db_healthy = db.integrity_check()
    return HealthResponse(
        status="ok" if db_healthy else "degraded",
        db_integrity=db_healthy,
        uptime_seconds=(datetime.now() - _server_start_time).total_seconds(),
    )


@app.get("/stats", response_model=APIResponse)
async def get_stats(api_key: str = Depends(get_api_key)):
    return APIResponse(
        data=DBHelper().get_ledger_stats(), trace_id=TraceContext.get_trace_id()
    )


@app.post("/webhook/feishu", response_model=APIResponse)
async def feishu_webhook(request: Request, background_tasks: BackgroundTasks):
    payload = await request.json()
    if "challenge" in payload:
        return {"challenge": payload["challenge"]}
    if "action" in payload:
        background_tasks.add_task(
            AsyncTaskProcessor.process_webhook_action,
            trans_id=payload["action"].get("parameters", {}).get("trans_id"),
            action_val=payload["action"].get("value"),
            trace_id=TraceContext.get_trace_id(),
        )
        return APIResponse(msg="Accepted", data={"toast": {"content": "Processing..."}})
    return APIResponse(msg="No action required")


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(api_key: str = Depends(get_api_key)):
    db = DBHelper()
    with db.transaction() as session:
        # 最近一小时交易量
        cutoff = func.now() - text("INTERVAL '1 hour'")
        recent_tx = (
            session.query(Transaction).filter(Transaction.created_at > cutoff).count()
        )

        # 服务状态
        svc_stats_objs = session.query(SysStatus).all()
        svc_stats = []
        for s in svc_stats_objs:
            svc_stats.append(
                {
                    "service_name": s.service_name,
                    "last_heartbeat": s.last_heartbeat,
                    "status": s.status,
                    "metrics": s.metrics,
                }
            )

    return render_dashboard(
        db.get_ledger_stats(),
        db.get_roi_metrics(),
        db.get_roi_weekly_trend(),
        getattr(db, "_archived_count", 0),
        getattr(db, "_global_total_amount", 0.0),
        recent_tx,
        svc_stats,
    )


def start_server(host="0.0.0.0", port=None):
    if port is None:
        port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host=host, port=port, log_config=None)


if __name__ == "__main__":
    start_server()
