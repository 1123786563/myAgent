import abc
from typing import Dict, Any


class BaseLLM(abc.ABC):
    @abc.abstractmethod
    def generate_response(
        self, prompt: str, system_role: str = "assistant", images: list[str] = None
    ) -> dict:
        """
        Generate a structured response from the LLM.
        Expected return format:
        {
            "reasoning": "Step-by-step thinking...",
            "result": "Final Answer",
            "confidence": 0.95
        }

        Args:
            prompt: Text prompt
            system_role: System instruction role
            images: List of image paths or base64 strings (for multimodal models)
        """
        pass

    @abc.abstractmethod
    def generate_embedding(self, text: str) -> list[float]:
        """
        Generate a vector embedding for the given text.
        """
        pass
