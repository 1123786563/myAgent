from fastapi import FastAPI, HTTPException, Request, BackgroundTasks, Header, status, Depends
from fastapi.security import APIKeyHeader
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import uvicorn
import os
import json
import hashlib
import hmac
from datetime import datetime
from logger import get_logger
from interaction_hub import InteractionHub
from db_helper import DBHelper
from config_manager import ConfigManager
from trace_context import TraceContext

log = get_logger("APIServer")
app = FastAPI(
    title="LedgerAlpha API",
    version="v1.0",
    description="AI-Powered Accounting Automation System"
)

# [Optimization Round 5] API 安全鉴权
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

async def get_api_key(api_key: str = Depends(api_key_header)):
    expected_key = ConfigManager.get("api.admin_key", "ledger-secret-2025")
    if api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials"
        )
    return api_key

# ==================== [Optimization Iteration 7] 结构化响应模型 ====================

class APIResponse(BaseModel):
    """统一 API 响应格式"""
    code: int = Field(0, description="状态码，0 表示成功")
    msg: str = Field("Success", description="状态消息")
    data: Optional[Dict[str, Any]] = Field(None, description="响应数据")
    trace_id: Optional[str] = Field(None, description="请求追踪 ID")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    db_integrity: bool
    uptime_seconds: Optional[float] = None
    version: str = "v1.0"


class ErrorResponse(BaseModel):
    """错误响应格式"""
    code: int
    msg: str
    detail: Optional[str] = None
    trace_id: Optional[str] = None


# ==================== [Optimization Iteration 7] 异步任务处理器 ====================

class AsyncTaskProcessor:
    """
    异步任务处理器 - 将耗时操作放入后台执行
    """

    @staticmethod
    def process_webhook_action(
        trans_id: int,
        action_val: str,
        trace_id: str,
        user_role: str = "ADMIN"
    ):
        """后台处理 Webhook 回调动作"""
        with TraceContext.start_trace(trace_id):
            with TraceContext.start_span("webhook_action_processing", {
                "trans_id": trans_id,
                "action": action_val
            }):
                try:
                    hub = InteractionHub()
                    success = hub.handle_callback(
                        transaction_id=trans_id,
                        action_value=action_val,
                        provided_trace_id=trace_id,
                        original_trace_id=trace_id,
                        user_role=user_role,
                    )
                    if success:
                        log.info(f"Webhook 动作处理成功: trans_id={trans_id}, action={action_val}",
                                extra={"trace_id": trace_id})
                    else:
                        log.warning(f"Webhook 动作处理失败: trans_id={trans_id}",
                                   extra={"trace_id": trace_id})
                except Exception as e:
                    log.error(f"Webhook 后台处理异常: {e}", extra={"trace_id": trace_id})


# ==================== [Optimization Iteration 7] 全局异常处理 ====================

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """统一 HTTP 异常处理"""
    trace_id = TraceContext.get_trace_id() or "N/A"
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            code=exc.status_code,
            msg=exc.detail,
            trace_id=trace_id
        ).model_dump()
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """统一通用异常处理"""
    trace_id = TraceContext.get_trace_id() or "N/A"
    log.error(f"未处理异常: {exc}", extra={"trace_id": trace_id}, exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            code=500,
            msg="Internal Server Error",
            detail=str(exc) if ConfigManager.get_bool("api.expose_errors", False) else None,
            trace_id=trace_id
        ).model_dump()
    )


# ==================== [Optimization Iteration 7] 请求中间件 ====================

@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    """为每个请求注入 TraceContext"""
    # 从请求头获取或生成 trace_id
    trace_id = request.headers.get("X-Trace-ID") or TraceContext._generate_trace_id()

    with TraceContext.start_trace(trace_id):
        TraceContext.set_attribute("http.method", request.method)
        TraceContext.set_attribute("http.path", request.url.path)

        start_time = datetime.now()
        response = await call_next(request)
        duration_ms = (datetime.now() - start_time).total_seconds() * 1000

        TraceContext.set_attribute("http.status_code", response.status_code)
        TraceContext.set_attribute("http.duration_ms", duration_ms)

        # 在响应头中返回 trace_id
        response.headers["X-Trace-ID"] = trace_id

        log.info(f"{request.method} {request.url.path} -> {response.status_code} ({duration_ms:.1f}ms)",
                extra={"trace_id": trace_id})

        return response


class WebhookPayload(BaseModel):
    """适配飞书/Slack 的通用 Webhook 结构"""
    uuid: Optional[str] = None
    token: Optional[str] = None
    challenge: Optional[str] = None
    type: Optional[str] = None
    event: Optional[Dict[str, Any]] = None
    action: Optional[Dict[str, Any]] = None  # 飞书卡片回调


# ==================== 服务启动时间记录 ====================
_server_start_time = datetime.now()


def verify_feishu_signature(timestamp: str, nonce: str, body: bytes, signature: str) -> bool:
    """
    [Security] Verify Feishu/Lark webhook signature (HMAC-SHA256)
    """
    secret = ConfigManager.get("feishu.encrypt_key", "")
    if not secret:
        log.warning("Feishu encrypt_key not configured, skipping signature check.")
        return True

    # Feishu signature format: sha256(timestamp + nonce + encrypt_key + body)
    content = timestamp + nonce + secret + body.decode("utf-8")
    expected_sig = hashlib.sha256(content.encode("utf-8")).hexdigest()

    if expected_sig != signature:
        log.error(f"Signature mismatch! Expected: {expected_sig}, Got: {signature}")
        return False
    return True


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """
    [Optimization Iteration 7] 增强健康检查端点
    """
    trace_id = TraceContext.get_trace_id()
    with TraceContext.start_span("health_check"):
        db = DBHelper()
        db_healthy = db.integrity_check()
        uptime = (datetime.now() - _server_start_time).total_seconds()

        return HealthResponse(
            status="ok" if db_healthy else "degraded",
            db_integrity=db_healthy,
            uptime_seconds=uptime,
            version="v1.0"
        )


@app.get("/stats", response_model=APIResponse)
async def get_stats(api_key: str = Depends(get_api_key)):
    """
    [Optimization Iteration 7] 增强统计端点 (带鉴权)
    """
    trace_id = TraceContext.get_trace_id()
    with TraceContext.start_span("get_stats"):
        db = DBHelper()
        stats = db.get_ledger_stats()

        return APIResponse(
            code=0,
            msg="Success",
            data=stats,
            trace_id=trace_id
        )


@app.get("/metrics/summary", response_model=APIResponse)
async def get_metrics_summary(api_key: str = Depends(get_api_key)):
    """
    [Optimization Iteration 7] 系统指标摘要端点 (带鉴权)
    """
    trace_id = TraceContext.get_trace_id()
    with TraceContext.start_span("get_metrics_summary"):
        try:
            from metrics_exporter import MetricsCollector
            from llm_connector import TokenBudgetManager

            collector = MetricsCollector()
            budget_mgr = TokenBudgetManager()

            db = DBHelper()
            db_stats = db.get_connection_stats()
            trace_stats = TraceContext.get_stats()
            llm_stats = budget_mgr.get_stats()

            return APIResponse(
                code=0,
                msg="Success",
                data={
                    "database": db_stats,
                    "tracing": trace_stats,
                    "llm": llm_stats,
                    "uptime_seconds": (datetime.now() - _server_start_time).total_seconds()
                },
                trace_id=trace_id
            )
        except Exception as e:
            log.warning(f"获取指标摘要失败: {e}", extra={"trace_id": trace_id})
            return APIResponse(
                code=500,
                msg="Failed to collect metrics",
                trace_id=trace_id
            )


@app.post("/webhook/feishu", response_model=APIResponse)
async def feishu_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_lark_request_timestamp: str = Header(None),
    x_lark_request_nonce: str = Header(None),
    x_lark_signature: str = Header(None),
):
    """
    [Optimization Iteration 7] 增强飞书卡片交互回调处理
    - 使用 BackgroundTasks 异步处理耗时操作
    - 结构化响应格式
    - 完整的 TraceContext 集成
    """
    trace_id = TraceContext.get_trace_id()
    body_bytes = await request.body()

    try:
        payload = json.loads(body_bytes)
    except json.JSONDecodeError:
        return APIResponse(code=400, msg="Invalid JSON", trace_id=trace_id)

    # 1. Security Check
    if x_lark_signature:
        if not verify_feishu_signature(
            x_lark_request_timestamp, x_lark_request_nonce, body_bytes, x_lark_signature
        ):
            return APIResponse(code=403, msg="Invalid Signature", trace_id=trace_id)

    log.info(f"收到 Webhook 回调: {payload}", extra={"trace_id": trace_id})

    # 2. URL 验证 (Feishu Challenge)
    if "challenge" in payload:
        return {"challenge": payload["challenge"]}

    # 3. 处理卡片 Action
    if "action" in payload:
        action_val = payload["action"].get("value")  # e.g. "CONFIRM"
        params = payload["action"].get("parameters", {})  # e.g. {"trans_id": 123}

        trans_id = params.get("trans_id")
        action_trace_id = params.get("trace_id", trace_id)

        if not trans_id:
            return APIResponse(code=400, msg="Missing transaction_id", trace_id=trace_id)

        # [Optimization Iteration 7] 使用 BackgroundTasks 异步处理
        background_tasks.add_task(
            AsyncTaskProcessor.process_webhook_action,
            trans_id=trans_id,
            action_val=action_val,
            trace_id=action_trace_id,
            user_role="ADMIN"
        )

        return APIResponse(
            code=0,
            msg="Accepted",
            data={"toast": {"content": "LedgerAlpha 已收到您的指令，正在处理中..."}},
            trace_id=trace_id
        )

    return APIResponse(code=0, msg="No action required", trace_id=trace_id)


@app.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(api_key: str = Depends(get_api_key)):
    """
    [Optimization Round 10/12/20/21] 增强型可视化仪表盘 (带 ROI 趋势与鉴权)
    """
    db = DBHelper()
    stats = db.get_ledger_stats()
    roi = db.get_roi_metrics()
    trend = db.get_roi_weekly_trend()
    
    # 格式化 7 天趋势
    trend_html = " | ".join([f"{t['report_date'][-2:]}日:{t['human_hours_saved']}h" for t in reversed(trend)])
    
    rows_html = "".join([
        f"<tr><td>{s['status']}</td><td>{s['count']}</td><td>￥{s['total_amount'] or 0:,.2f}</td></tr>" 
        for s in stats
    ])
    
    roi_html = f"""
    <div style="background: #e7f3ff; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
        <h2 style="margin-top: 0;">💰 效益快报 (ROI)</h2>
        <p>累计节省人工: <b>{roi.get('human_hours_saved', 0)}</b> 小时</p>
        <p>今日 Token 支出: <b>${roi.get('token_cost_usd', 0):.4f}</b></p>
        <p>当前 ROI 系数: <b>{roi.get('roi_ratio', 0)}</b> (1h/$)</p>
        <p style="font-size: 0.9em; color: #555;"><b>最近 7 天趋势:</b> {trend_html}</p>
    </div>
    """
    
    html_content = f"""
    <html>
        <head><title>LedgerAlpha Dashboard</title></head>
        <body style="font-family: sans-serif; padding: 20px; max-width: 800px; margin: auto;">
            <h1>🐶 LedgerAlpha 运行看板</h1>
            {roi_html}
            <table border="1" style="width: 100%; text-align: left; border-collapse: collapse;">
                <tr style="background: #f2f2f2;"><th>状态</th><th>笔数</th><th>合计金额</th></tr>
                {rows_html}
            </table>
            <p style="color: #666;">系统版本: v1.3.1 | 最后更新: {datetime.now().strftime('%H:%M:%S')}</p>
        </body>
    </html>
    """
    return html_content

def start_server(host="0.0.0.0", port=8000):
    log.info(f"启动 API Server @ {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_config=None)


if __name__ == "__main__":
    start_server()
