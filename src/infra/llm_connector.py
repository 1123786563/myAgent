from core.config_manager import ConfigManager
from infra.logger import get_logger
from infra.llm_base import BaseLLM
from infra.llm_openai import OpenAICompatibleLLM
from infra.llm_mock import MockOpenManusLLM

log = get_logger("LLMFactory")

class LLMFactory:
    """
    [Optimization Iteration 2] 增强的 LLM 工厂
    """
    _instances = {}

    @staticmethod
    def get_llm(llm_type: str = None) -> BaseLLM:
        if llm_type is None:
            llm_type = ConfigManager.get("llm.type", "OPENAI")
        llm_type = llm_type.upper()

        if llm_type in LLMFactory._instances:
            return LLMFactory._instances[llm_type]

        if llm_type == "OPENAI":
            instance = OpenAICompatibleLLM()
        else:
            instance = MockOpenManusLLM()

        LLMFactory._instances[llm_type] = instance
        return instance

    @staticmethod
    def reset():
        LLMFactory._instances.clear()
