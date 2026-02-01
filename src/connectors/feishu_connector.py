import json
import os
from typing import Optional, Dict, Any
from infra.logger import get_logger
from core.config_manager import ConfigManager
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

try:
    import lark_oapi as lark
    from lark_oapi.api.im.v1 import *
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False

log = get_logger("FeishuConnector")


class FeishuConnector:
    """
    飞书连接器 - 使用lark_oapi SDK实现
    """
    
    def __init__(self):
        # SDK配置
        self.app_id = ConfigManager.get("feishu.app_id") or os.getenv("FEISHU_APP_ID")
        self.app_secret = ConfigManager.get("feishu.app_secret") or os.getenv("FEISHU_APP_SECRET")
        self.app_ticket = ConfigManager.get("feishu.app_ticket") or os.getenv("FEISHU_APP_TICKET")
        
        # 初始化SDK客户端
        self._client = None
        self._init_sdk_client()
        
        # 调试信息
        log.info(f"Feishu SDK available: {SDK_AVAILABLE}")
        log.info(f"Feishu SDK configured: {bool(self.app_id and self.app_secret)}")

    def _init_sdk_client(self):
        """初始化飞书SDK客户端"""
        if not SDK_AVAILABLE:
            log.error("lark_oapi SDK not installed")
            return
            
        if not self.app_id or not self.app_secret:
            log.error("Feishu SDK credentials not configured")
            return
            
        try:
            # 根据示例代码构建客户端
            self._client = lark.Client.builder() \
                .app_id(self.app_id) \
                .app_secret(self.app_secret) \
                .domain(lark.FEISHU_DOMAIN) \
                .timeout(3) \
                .app_type(lark.AppType.ISV) \
                .app_ticket(self.app_ticket or "") \
                .enable_set_token(False) \
                .log_level(lark.LogLevel.DEBUG) \
                .build()
                
            log.info("Feishu SDK client initialized successfully")
        except Exception as e:
            log.error(f"Failed to initialize Feishu SDK client: {e}")
            self._client = None
            
        # 添加调试信息
        log.debug(f"SDK Available: {SDK_AVAILABLE}")
        log.debug(f"App ID configured: {bool(self.app_id)}")
        log.debug(f"App Secret configured: {bool(self.app_secret)}")
        log.debug(f"App Ticket configured: {bool(self.app_ticket)}")
        log.debug(f"Client initialized: {self._client is not None}")

    def send_card(self, card_content: dict, receive_id: str, receive_id_type: str = "open_id") -> bool:
        """
        使用SDK发送消息卡片
        
        Args:
            card_content: 卡片内容
            receive_id: 接收者ID
            receive_id_type: 接收者ID类型 (open_id, user_id, union_id, email)
        """
        if not self._client:
            log.error("SDK client not initialized, cannot send card")
            return False
            
        if not receive_id:
            log.error("receive_id is required for SDK sending")
            return False
            
        try:
            # 构建请求
            request = CreateMessageRequest.builder() \
                .receive_id_type(receive_id_type) \
                .request_body(CreateMessageRequestBody.builder()
                    .receive_id(receive_id)
                    .msg_type("interactive")
                    .content(json.dumps({"card": card_content}))
                    .build()) \
                .build()
                
            # 发送消息
            response = self._client.im.v1.message.create(request)
            
            if response.success():
                log.info(f"Card sent successfully via SDK, message_id: {response.data.message_id}")
                return True
            else:
                log.error(f"Failed to send card via SDK: {response.msg}")
                return False
                
        except Exception as e:
            log.error(f"Exception when sending card via SDK: {e}")
            return False

    def transform_internal_to_feishu(self, internal_card: dict) -> dict:
        """将内部卡片格式转换为飞书卡片格式"""
        header = internal_card.get("header", {})
        body = internal_card.get("body", {})
        actions = internal_card.get("actions", [])
        inputs = internal_card.get("inputs", [])
        metadata = internal_card.get("metadata", {})

        feishu_card = {
            "config": {"update_multi": True},
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": header.get("title", "LedgerAlpha 通知"),
                },
                "template": "blue" if header.get("style") == "primary" else "orange",
            },
            "elements": [],
        }

        if body.get("content"):
            feishu_card["elements"].append(
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": body.get("content")},
                }
            )

        for img_id in body.get("images", []):
            feishu_card["elements"].append(
                {
                    "tag": "img",
                    "img_key": img_id,
                    "alt": {"tag": "plain_text", "content": "image"},
                }
            )

        for inp in inputs:
            feishu_card["elements"].append(
                {
                    "tag": "input",
                    "name": inp.get("id"),
                    "placeholder": {
                        "tag": "plain_text",
                        "content": inp.get("placeholder", "Please enter"),
                    },
                    "label": {"tag": "plain_text", "content": inp.get("label", "")},
                }
            )

        if actions:
            action_elements = []
            for btn in actions:
                btn_style = "primary"
                if btn.get("style") == "success":
                    btn_style = "primary"
                elif btn.get("style") == "danger":
                    btn_style = "danger"
                elif btn.get("style") == "warning":
                    btn_style = "default"

                action_elements.append(
                    {
                        "tag": "button",
                        "text": {
                            "tag": "plain_text",
                            "content": btn.get("label", "Confirm"),
                        },
                        "type": btn_style,
                        "value": {**metadata, "action": btn.get("value")},
                    }
                )

            feishu_card["elements"].append(
                {"tag": "action", "actions": action_elements}
            )

        return feishu_card