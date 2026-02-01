import abc
from typing import Dict, Any

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
