import abc
import json
import time
import random
from logger import get_logger

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
    """

    def __init__(self):
        self.knowledge_base = {
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

    def generate_response(self, prompt: str, system_role: str = "assistant") -> dict:
        """
        Simulate a reasoned response.
        """
        log.info(f"Simulating OpenManus reasoning for prompt: {prompt[:50]}...")
        time.sleep(1.0)  # Simulate network latency

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
