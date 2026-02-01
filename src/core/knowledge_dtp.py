from typing import Dict, Any

class DTPResponse:
    """[Suggestion 1] 决策传输协议 (Decision Transfer Protocol)"""
    def __init__(self, raw_data: Dict[Any, Any]):
        self.entity = raw_data.get("entity")
        self.category = raw_data.get("category")
        self.confidence = raw_data.get("confidence", 0.0)
        self.reasoning = raw_data.get("reasoning", "")
        self.is_tax_related = raw_data.get("is_tax_related", False)
        self.payment_milestones = raw_data.get("payment_milestones", [])
        self.contract_terms = raw_data.get("contract_terms", {})
