import os
import sys
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.append(src_path)

from connectors.feishu_connector import FeishuConnector
from api.interaction_hub import InteractionHub
from core.config_manager import ConfigManager


def test_sdk_push(receive_id=None, receive_id_type="open_id"):
    """测试SDK方式发送"""
    print("--- Test: SDK FeishuConnector Push ---")
    connector = FeishuConnector()
    
    if not connector._client:
        print("❌ SDK not initialized. Check your SDK credentials.")
        return False
        
    if not receive_id:
        print("❌ Error: receive_id is required for SDK sending")
        print("Usage: python3 scripts/test_feishu_push.py RECEIVE_ID [RECEIVE_ID_TYPE]")
        return False

    interactive_card = {
        "header": {
            "title": {"tag": "plain_text", "content": "LedgerAlpha SDK Test"},
            "template": "green",
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "**Hello!** This is an integration test from LedgerAlpha via SDK.",
                },
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "SDK Test Button"},
                        "type": "primary",
                        "value": {"sdk_test": True},
                    }
                ],
            },
        ],
    }

    success = connector.send_card(interactive_card, receive_id=receive_id, receive_id_type=receive_id_type)
    if success:
        print("✅ SDK Success! Check your Feishu.")
        return True
    else:
        print("❌ SDK Failed. Check credentials and receive_id.")
        return False


def test_hub_push(receive_id=None):
    print("\n--- Test: InteractionHub Push ---")
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
    # 注意：如果InteractionHub也使用SDK方式，需要确保传递receive_id
    if hasattr(hub.feishu, 'send_card') and receive_id:
        # 如果SDK方式需要receive_id，这里需要传递
        # 但由于hub.push_card接口可能没有receive_id参数，这里需要适配
        print("Note: Make sure InteractionHub is configured for SDK mode with receive_id")
    
    hub.push_card(
        transaction_id=999, proposal_data=test_proposal, trace_id="test_trace_id"
    )
    print("✅ Method called.")


def test_configuration():
    """测试配置信息"""
    print("\n--- Configuration Info ---")
    print(f"SDK Available: { hasattr(FeishuConnector(), '_client') }")
    print(f"SDK App ID configured: { bool(ConfigManager.get('feishu.app_id') or os.getenv('FEISHU_APP_ID')) }")
    print(f"SDK App Secret configured: { bool(ConfigManager.get('feishu.app_secret') or os.getenv('FEISHU_APP_SECRET')) }")
    print(f"SDK App Ticket configured: { bool(ConfigManager.get('feishu.app_ticket') or os.getenv('FEISHU_APP_TICKET')) }")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Error: Missing required arguments.")
        print("Usage: python3 scripts/test_feishu_push.py RECEIVE_ID [RECEIVE_ID_TYPE]")
        print("\nExample:")
        print("  python3 scripts/test_feishu_push.py user_open_id open_id")
        print("  python3 scripts/test_feishu_push.py user_email email")
        sys.exit(1)

    receive_id = sys.argv[1]
    receive_id_type = sys.argv[2] if len(sys.argv) > 2 else "open_id"

    # 显示配置信息
    test_configuration()
    
    # 检查SDK配置
    sdk_available = ConfigManager.get("feishu.app_id") or os.getenv("FEISHU_APP_ID")
    
    if not sdk_available:
        print("\nError: Feishu SDK not configured.")
        print("Please set the following environment variables in .env:")
        print("  FEISHU_APP_ID=your_app_id_here")
        print("  FEISHU_APP_SECRET=your_app_secret_here")
        print("  FEISHU_APP_TICKET=your_app_ticket_here (optional)")
        sys.exit(1)

    # 执行测试
    success = test_sdk_push(receive_id, receive_id_type)
    test_hub_push(receive_id if success else None)
    
    if success:
        print("\n✅ All tests completed successfully!")
    else:
        print("\n❌ Some tests failed. Check the logs for details.")