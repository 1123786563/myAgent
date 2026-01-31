import uuid
from bus_init import LedgerMsg

class OpenManusAnalyst:
    """模拟 OpenManus 的强推理能力"""
    def __init__(self):
        self.name = "OpenManusSpecialForce"

    def investigate(self, raw_data_context):
        print(f"[{self.name}] 正在激活强推理，联网搜索市场信息...")
        # 模拟联网搜索和推理过程
        # 假设我们收到了一个"玄铁重剑"的单据
        if "玄铁重剑" in raw_data_context:
            return {
                "category": "办公费用-福利费",
                "reason": "联网查得：玄铁重剑为健身器材，单价低于固定资产标准，建议计入福利费。",
                "confidence": 0.95,
                "new_rule": {"keyword": "玄铁重剑", "category": "办公费用-福利费"}
            }
        return {
            "category": "待核核定-需要人工",
            "reason": "强推理后仍无法确定，建议人工核查。",
            "confidence": 0.1
        }

if __name__ == "__main__":
    analyst = OpenManusAnalyst()
    print(analyst.investigate("收到一张玄铁重剑的发票，金额 500 元"))
