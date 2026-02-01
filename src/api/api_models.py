from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime

class APIResponse(BaseModel):
    code: int = Field(0, description="状态码，0 表示成功")
    msg: str = Field("Success", description="状态消息")
    data: Optional[Dict[str, Any]] = Field(None, description="响应数据")
    trace_id: Optional[str] = Field(None, description="请求追踪 ID")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())

class HealthResponse(BaseModel):
    status: str
    db_integrity: bool
    uptime_seconds: Optional[float] = None
    version: str = "v1.0"

class ErrorResponse(BaseModel):
    code: int
    msg: str
    detail: Optional[str] = None
    trace_id: Optional[str] = None

class WebhookPayload(BaseModel):
    uuid: Optional[str] = None
    token: Optional[str] = None
    challenge: Optional[str] = None
    type: Optional[str] = None
    event: Optional[Dict[str, Any]] = None
    action: Optional[Dict[str, Any]] = None
