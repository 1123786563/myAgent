import os
import sys

src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.append(src_path)

from connectors.feishu_connector import FeishuConnector
from api.interaction_hub import InteractionHub
from core.config_manager import ConfigManager


def test_raw_push(webhook_url=None):
    print("--- Test 1: Raw FeishuConnector Push ---")
    connector = FeishuConnector()
    if webhook_url:
        connector.webhook_url = webhook_url

    interactive_card = {
        "header": {
            "title": {"tag": "plain_text", "content": "LedgerAlpha Integration Test"},
            "template": "blue",
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "**Hello!** This is an integration test from LedgerAlpha.",
                },
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "Test Button"},
                        "type": "primary",
                        "value": {"test": True},
                    }
                ],
            },
        ],
    }

    success = connector.send_card(interactive_card)
    if success:
        print("✅ Success! Check your Feishu.")
    else:
        print("❌ Failed. Check Webhook URL and Network.")


def test_hub_push():
    print("\n--- Test 2: InteractionHub Push ---")
    hub = InteractionHub()
    if not hub.im_enabled:
        print("⚠️ Warning: IM disabled, forcing enable for test...")
        hub.im_enabled = True
        if not hub.feishu:
            hub.feishu = FeishuConnector()

    test_proposal = {
        "vendor": "Test Vendor",
        "amount": 1234.56,
        "category": "6601-01 Office Supplies",
        "reason": "Testing auto-push logic",
    }

    print("Pushing simulated approval card...")
    hub.push_card(
        transaction_id=999, proposal_data=test_proposal, trace_id="test_trace_id"
    )
    print("✅ Method called.")


if __name__ == "__main__":
    custom_url = sys.argv[1] if len(sys.argv) > 1 else None

    if not custom_url and not ConfigManager.get("im.feishu.webhook_url"):
        print("Error: No Webhook URL found.")
        print("Usage: python3 scripts/test_feishu_push.py [YOUR_WEBHOOK_URL]")
        sys.exit(1)

    test_raw_push(custom_url)
    test_hub_push()
