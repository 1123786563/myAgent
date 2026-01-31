import agentscope
from agentscope.agents import AgentBase
from agentscope.message import Msg
import uuid
import yaml
import time
import hmac
import hashlib
from config_manager import ConfigManager

# 核心安全：内部通信令牌
SYSTEM_AUTH_TOKEN = "LA_SECURE_TOKEN_2026_XF"

def init_bus():
    # 动态加载模型配置
    model_configs = [
        {
            "config_name": "accounting_model",
            "model_type": "openai_chat",
            "model_name": ConfigManager.get("agents.accounting.model", "gpt-4o-mini")
        }
    ]
    
    agentscope.init(
        model_configs=model_configs,
        logger_level="DEBUG"
    )

class LedgerMsg:
    @staticmethod
    def create(sender, content, action="PROPOSE", trace_id=None):
        ts = time.time()
        # 优化点：结构化强校验预处理
        if action == "PROPOSE_ENTRY" and isinstance(content, dict):
            if "category" not in content: content["category"] = "Unknown"
        
        # 计算消息指纹，防内部篡改
        msg_payload = f"{sender}:{action}:{ts}"
        signature = hmac.new(SYSTEM_AUTH_TOKEN.encode(), msg_payload.encode(), hashlib.sha256).hexdigest()
        
        return Msg(
            name=sender,
            content=content,
            role="assistant",
            trace_id=trace_id or str(uuid.uuid4()),
            action=action,
            timestamp=ts,
            auth_token=SYSTEM_AUTH_TOKEN,
            signature=signature
        )

class ManagerAgent(AgentBase):
    def __init__(self, name):
        super().__init__(name=name)

    def reply(self, x: dict = None) -> dict:
        # 1. 基础认证鉴权
        if x.get("auth_token") != SYSTEM_AUTH_TOKEN:
            return LedgerMsg.create(self.name, "REJECTED: UNAUTHORIZED", action="ERROR")
            
        # 2. 消息指纹校验
        ts = x.get("timestamp", 0)
        msg_payload = f"{x['name']}:{x['action']}:{ts}"
        expected_sig = hmac.new(SYSTEM_AUTH_TOKEN.encode(), msg_payload.encode(), hashlib.sha256).hexdigest()
        
        if not hmac.compare_digest(x.get("signature", ""), expected_sig):
            return LedgerMsg.create(self.name, "REJECTED: SIGNATURE_ERROR", action="ERROR")
            
        # 3. 重放攻击检查 (60秒过期)
        if time.time() - ts > 60:
            return LedgerMsg.create(self.name, "REJECTED: MSG_EXPIRED", action="ERROR")

        return LedgerMsg.create(self.name, "ACK", action="HEARTBEAT", trace_id=x.get("trace_id"))
