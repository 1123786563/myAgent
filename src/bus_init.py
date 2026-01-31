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
    _global_seq = 0
    _lock = threading.Lock()

    @staticmethod
    def create(sender, content, action="PROPOSE", trace_id=None, sender_role="GUEST"):
        ts = time.time()
        
        # [Optimization 3] 引入逻辑时钟 (Lamport Clock) 序列号
        with LedgerMsg._lock:
            LedgerMsg._global_seq += 1
            seq_num = LedgerMsg._global_seq

        # 优化点：结构化强校验预处理
        # ... (保持原有校验逻辑)
        if action == "PROPOSE_ENTRY" and isinstance(content, dict):
            if "category" not in content: content["category"] = "Unknown"
        
        # 计算消息指纹，加入 role 和 seq_num 绑定 (Optimization 3)
        msg_payload = f"{sender}:{sender_role}:{action}:{seq_num}:{ts}"
        signature = hmac.new(SYSTEM_AUTH_TOKEN.encode(), msg_payload.encode(), hashlib.sha256).hexdigest()
        
        return Msg(
            name=sender,
            content=content,
            role="assistant",
            sender_role=sender_role,
            seq_num=seq_num, # [Optimization 3]
            trace_id=trace_id or str(uuid.uuid4()),
            action=action,
            timestamp=ts,
            auth_token=SYSTEM_AUTH_TOKEN,
            signature=signature
        )

class ManagerAgent(AgentBase):
    def __init__(self, name):
        super().__init__(name=name)
        from db_helper import DBHelper
        self.db = DBHelper()
        self._load_permissions()

    def _load_permissions(self):
        """[Optimization 1] 从数据库动态加载权限矩阵"""
        try:
            with self.db.transaction("DEFERRED") as conn:
                rows = conn.execute("SELECT role_name, action_name FROM sys_permissions").fetchall()
                self.role_permissions = {}
                for row in rows:
                    role = row['role_name']
                    action = row['action_name']
                    if role not in self.role_permissions:
                        self.role_permissions[role] = []
                    self.role_permissions[role].append(action)
            log.info(f"成功加载动态权限矩阵: {len(self.role_permissions)} 个角色")
        except Exception as e:
            log.error(f"权限加载失败，回退至静态配置: {e}")
            self.role_permissions = {
                "ACCOUNTANT": ["PROPOSE_ENTRY"],
                "AUDITOR": ["AUDIT_RESULT"],
                "MASTER": ["HEARTBEAT"]
            }

    def reply(self, x: dict = None) -> dict:
        # ... (保持原有的重载信号处理)
        if x.get("action") == "RELOAD_PERMISSIONS":
            self._load_permissions()
            return LedgerMsg.create(self.name, "PERMISSIONS_RELOADED", action="ACK", sender_role="MASTER")

        # [Optimization 3] 消息分级优先级处理
        action = x.get("action")
        # 优先列表：心跳 > 交互 > 异常自愈信号 > 审计结果 > 预记账
        priority_map = {
            "HEARTBEAT": 0,
            "INTERACTION_HUB_SIGNAL": 1,
            "STATE_RECOVERY_SIGNAL": 2,
            "AUDIT_RESULT": 3,
            "PROPOSE_ENTRY": 4
        }
        
        # [Optimization 2] 模拟消息持久化 Outbox 校验 (此处为逻辑预埋)
        if x.get("is_persistent"):
            log.debug(f"持久化消息入库校验: {x.get('trace_id')}")

        # 获取消息优先级，默认为 5
        msg_priority = priority_map.get(action, 5)
        # 模拟高优先级消息抢占逻辑 (此处为逻辑埋点)
        if msg_priority <= 1:
            log.debug(f"总控接收极高优先级任务: {action} (Priority: {msg_priority})")

        # 1. 基础认证鉴权
        # ... (保持后续逻辑)
        # ... (保持后续逻辑)
