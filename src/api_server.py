from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel
import uvicorn
import os
import json
from logger import get_logger
from interaction_hub import InteractionHub
from db_helper import DBHelper

log = get_logger("APIServer")
app = FastAPI(title="LedgerAlpha API", version="v1.0")

class WebhookPayload(BaseModel):
    # 适配飞书/Slack 的通用 Webhook 结构
    uuid: str = None
    token: str = None
    challenge: str = None
    type: str = None
    event: dict = None
    action: dict = None # 飞书卡片回调

@app.get("/health")
def health_check():
    db = DBHelper()
    db_healthy = db.integrity_check()
    return {"status": "ok", "db_integrity": db_healthy}

@app.get("/stats")
def get_stats():
    db = DBHelper()
    return db.get_ledger_stats()

@app.post("/webhook/feishu")
async def feishu_webhook(payload: dict, background_tasks: BackgroundTasks):
    """
    处理飞书卡片交互回调
    """
    log.info(f"收到 Webhook 回调: {payload}")
    
    # 1. URL 验证 (Feishu Challenge)
    if "challenge" in payload:
        return {"challenge": payload["challenge"]}
        
    # 2. 处理卡片 Action
    if "action" in payload:
        action_val = payload["action"].get("value") # e.g. "CONFIRM"
        params = payload["action"].get("parameters", {}) # e.g. {"trans_id": 123}
        
        trans_id = params.get("trans_id")
        trace_id = params.get("trace_id")
        
        if not trans_id:
            return {"code": 400, "msg": "Missing transaction_id"}

        hub = InteractionHub()
        # 异步处理，避免阻塞 Webhook 响应
        success = hub.handle_callback(
            transaction_id=trans_id,
            action_value=action_val,
            provided_trace_id=trace_id,
            original_trace_id=trace_id, # 简化校验
            user_role="ADMIN" # 假设来自飞书的都是 Admin
        )
        
        if success:
            return {"code": 0, "msg": "Success", "toast": {"content": "LedgerAlpha 已收到您的指令"}}
        else:
            return {"code": 500, "msg": "Failed", "toast": {"content": "处理失败，请查看日志"}}

    return {"code": 0}

def start_server(host="0.0.0.0", port=8000):
    log.info(f"启动 API Server @ {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_config=None)

if __name__ == "__main__":
    start_server()
