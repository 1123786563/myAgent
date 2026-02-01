import os
import time
from infra.logger import get_logger
from utils.project_paths import get_path
from infra.llm_base import BaseLLM

log = get_logger("MockOpenManusLLM")


class MockOpenManusLLM(BaseLLM):
    """
    Simulates the OpenManus Agent's L2 reasoning capability.
    """

    def __init__(self, kb_path: str = None):
        self.kb_path = kb_path or get_path("src", "l2_knowledge_base.yaml")
        self.knowledge_base = self._load_knowledge_base()
        self._kb_last_modified = self._get_file_mtime()

    def _get_file_mtime(self) -> float:
        try:
            return os.path.getmtime(self.kb_path)
        except OSError:
            return 0.0

    def _load_knowledge_base(self) -> dict:
        default_kb = {
            "aliyun": {
                "category": "技术服务费",
                "reason": "Cloud computing service provider",
            },
            "aws": {"category": "技术服务费", "reason": "Cloud infrastructure"},
            "starbucks": {
                "category": "业务招待费",
                "reason": "Coffee chain, likely client meeting",
            },
            "didi": {"category": "差旅费-交通费", "reason": "Ride hailing service"},
            "apple": {"category": "办公设备", "reason": "Electronics hardware"},
            "unknown": {
                "category": "杂项支出",
                "reason": "Low confidence classification",
            },
        }
        try:
            import yaml

            if os.path.exists(self.kb_path):
                with open(self.kb_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if data and "vendors" in data:
                        kb = {
                            v.get("keyword", "").lower(): {
                                "category": v.get("category", "杂项支出"),
                                "reason": v.get("reason", "Loaded from KB"),
                            }
                            for v in data["vendors"]
                            if v.get("keyword")
                        }
                        kb["unknown"] = default_kb["unknown"]
                        return kb
        except:
            pass
        return default_kb

    def generate_response(
        self, prompt: str, system_role: str = "assistant", images: list[str] = None
    ) -> dict:
        if images:
            return {
                "reasoning": "Simulated OCR analysis",
                "result": {
                    "category": "OCR识别结果",
                    "reason": "Image content processed",
                    "extracted_data": {
                        "amount": 100.00,
                        "date": "2023-01-01",
                        "vendor": "Simulated Vendor",
                    },
                },
                "confidence": 0.85,
            }

        curr_mtime = self._get_file_mtime()
        if curr_mtime > self._kb_last_modified:
            self.knowledge_base = self._load_knowledge_base()
            self._kb_last_modified = curr_mtime

        prompt_lower = prompt.lower()
        matched_key = next(
            (k for k in self.knowledge_base if k in prompt_lower), "unknown"
        )
        kb_entry = self.knowledge_base[matched_key]

        return {
            "reasoning": f"Simulated reasoning for {matched_key}",
            "result": {"category": kb_entry["category"], "reason": kb_entry["reason"]},
            "confidence": 0.95 if matched_key != "unknown" else 0.4,
        }

    def generate_embedding(self, text: str) -> list[float]:
        """Mock embedding generation (random vector for testing)"""
        import random

        # Standard OpenAI embedding size is 1536
        return [random.random() for _ in range(1536)]
