class ConsensusStrategy:
    """Consensus voting strategies"""
    STRICT = "STRICT"  # All must agree
    BALANCED = "BALANCED"  # Majority wins
    GROWTH = "GROWTH"  # One vote enough for small amounts

class ConsensusEngine:
    """
    [Optimization 3/19] Dynamic Consensus Engine
    """
    def __init__(self, strategy=ConsensusStrategy.BALANCED):
        self.strategy = strategy
        self.personas = {
            "COMPLIANCE": self._vote_compliance,
            "FINANCE": self._vote_finance,
            "TAX": self._vote_tax
        }

    def _vote_compliance(self, amount, category, vendor):
        if amount > 50000:
            return False, "Large amount requires contract"
        if any(x in category for x in ["赠送", "礼品", "回扣"]):
            return False, "Prohibited category"
        return True, "Pass"

    def _vote_finance(self, amount, category, vendor):
        if amount > 10000 and "研发" not in category:
            return False, "Budget restriction for non-R&D"
        return True, "Pass"

    def _vote_tax(self, amount, category, vendor):
        if "个人" in vendor and amount > 500:
            return False, "High individual payment risk"
        return True, "Pass"

    def vote(self, proposal):
        from utils.decimal_utils import to_decimal
        amount = to_decimal(proposal.get("amount", 0))
        category = proposal.get("category", "")
        vendor = proposal.get("vendor", "")
        votes = {}
        for name, func in self.personas.items():
            passed, reason = func(amount, category, vendor)
            votes[name] = {"pass": passed, "reason": reason}
        return votes

    def decide(self, votes):
        pass_count = sum(1 for v in votes.values() if v["pass"])
        total = len(votes)
        if self.strategy == ConsensusStrategy.STRICT:
            return pass_count == total
        elif self.strategy == ConsensusStrategy.GROWTH:
            return pass_count >= 1
        else:  # BALANCED
            return pass_count >= (total / 2)
