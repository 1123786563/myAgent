import json
import time
import hmac
import hashlib
import base64
import requests
from infra.logger import get_logger
from core.config_manager import ConfigManager

log = get_logger("FeishuConnector")


class FeishuConnector:
    def __init__(self):
        self.webhook_url = ConfigManager.get("im.feishu.webhook_url")
        self.secret = ConfigManager.get("im.feishu.secret")

    def _generate_signature(self, timestamp: str) -> str:
        if not self.secret:
            return ""
        string_to_sign = f"{timestamp}\n{self.secret}"
        hmac_code = hmac.new(
            string_to_sign.encode("utf-8"), digestmod=hashlib.sha256
        ).digest()
        return base64.b64encode(hmac_code).decode("utf-8")

    def send_card(self, card_content: dict) -> bool:
        if not self.webhook_url:
            log.warning("未配置 Feishu Webhook URL，跳过发送")
            return False

        timestamp = str(int(time.time()))
        payload = {
            "timestamp": timestamp,
            "msg_type": "interactive",
            "card": card_content,
        }

        if self.secret:
            payload["sign"] = self._generate_signature(timestamp)

        try:
            response = requests.post(
                self.webhook_url,
                headers={"Content-Type": "application/json"},
                data=json.dumps(payload),
                timeout=10,
            )
            response.raise_for_status()
            resp_json = response.json()
            if resp_json.get("code") == 0:
                log.info("Feishu 消息卡片发送成功")
                return True
            else:
                log.error(f"Feishu 发送失败: {resp_json}")
                return False
        except Exception as e:
            log.error(f"Feishu 连接异常: {e}")
            return False

    def transform_internal_to_feishu(self, internal_card: dict) -> dict:
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
