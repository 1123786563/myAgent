import abc
import json
import time
import random
import os
from logger import get_logger
from project_paths import get_path

log = get_logger("LLMConnector")


class BaseLLM(abc.ABC):
    @abc.abstractmethod
    def generate_response(self, prompt: str, system_role: str = "assistant") -> dict:
        """
        Generate a structured response from the LLM.
        Expected return format:
        {
            "reasoning": "Step-by-step thinking...",
            "result": "Final Answer",
            "confidence": 0.95
        }
        """
        pass


class MockOpenManusLLM(BaseLLM):
    """
    Simulates the OpenManus Agent's L2 reasoning capability.
    In production, this would connect to an actual LLM API (OpenAI/Anthropic).

    [Optimization] Now supports loading knowledge base from external YAML file.
    """

    def __init__(self, kb_path: str = None):
        self.kb_path = kb_path or get_path("src", "l2_knowledge_base.yaml")
        self.knowledge_base = self._load_knowledge_base()
        self._kb_last_modified = self._get_file_mtime()

    def _get_file_mtime(self) -> float:
        """Get file modification time for hot-reload detection."""
        try:
            return os.path.getmtime(self.kb_path)
        except OSError:
            return 0.0

    def _load_knowledge_base(self) -> dict:
        """
        Load knowledge base from external YAML file.
        Falls back to default hardcoded KB if file not found.
        """
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
                        kb = {}
                        for vendor in data["vendors"]:
                            key = vendor.get("keyword", "").lower()
                            if key:
                                kb[key] = {
                                    "category": vendor.get("category", "杂项支出"),
                                    "reason": vendor.get("reason", "Loaded from KB"),
                                }
                        kb["unknown"] = default_kb["unknown"]
                        log.info(f"已从外部知识库加载 {len(kb)-1} 条供应商映射规则")
                        return kb
        except Exception as e:
            log.warning(f"加载外部知识库失败，使用默认配置: {e}")

        return default_kb

    def _maybe_reload_kb(self):
        """Hot-reload knowledge base if file has changed."""
        current_mtime = self._get_file_mtime()
        if current_mtime > self._kb_last_modified:
            log.info("检测到知识库文件变更，执行热重载...")
            self.knowledge_base = self._load_knowledge_base()
            self._kb_last_modified = current_mtime

    def generate_response(self, prompt: str, system_role: str = "assistant") -> dict:
        """
        Simulate a reasoned response with hot-reload support.
        """
        # Check for KB updates before processing
        self._maybe_reload_kb()

        log.info(f"Simulating OpenManus reasoning for prompt: {prompt[:50]}...")
        time.sleep(0.5)  # Reduced latency simulation

        # Simple keyword matching to simulate "reasoning"
        prompt_lower = prompt.lower()
        matched_key = "unknown"
        for key in self.knowledge_base:
            if key in prompt_lower:
                matched_key = key
                break

        kb_entry = self.knowledge_base[matched_key]

        # Construct a "Chain of Thought" style response
        reasoning_steps = [
            f"1. Analyze input context: '{prompt[:30]}...'",
            f"2. Search internal knowledge base for keywords.",
            f"3. Found match: '{matched_key}'."
            if matched_key != "unknown"
            else "3. No direct match found, applying general heuristics.",
            f"4. Determine category based on business nature: {kb_entry['category']}.",
            f"5. Final verification against accounting standards.",
        ]

        response = {
            "reasoning": "\n".join(reasoning_steps),
            "result": {"category": kb_entry["category"], "reason": kb_entry["reason"]},
            "confidence": 0.95 if matched_key != "unknown" else 0.4,
        }

        return response


class LLMFactory:
    @staticmethod
    def get_llm(type: str = "MOCK"):
        if type == "MOCK":
            return MockOpenManusLLM()
        else:
            raise NotImplementedError(f"LLM type {type} not implemented")
