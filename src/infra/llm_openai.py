import json
import time
import random
import re
import hashlib
from typing import Optional, Tuple, Dict, Any
from infra.llm_base import BaseLLM
from infra.llm_budget import TokenBudgetManager
from infra.llm_cache import _response_cache
from infra.logger import get_logger
from core.config_manager import ConfigManager
from infra.trace_context import TraceContext

log = get_logger("OpenAICompatibleLLM")


class OpenAICompatibleLLM(BaseLLM):
    """
    [Optimization Iteration 2] 真实 LLM API 接入
    """

    def __init__(self):
        self.base_url = ConfigManager.get("llm.base_url", "http://127.0.0.1:8045/v1")
        self.api_key = ConfigManager.get("llm.api_key")
        self.model = ConfigManager.get("llm.model", "gemini-3-flash")
        self.fallback_model = ConfigManager.get("llm.fallback_model", "gpt-4o-mini")
        self._using_fallback = False
        self.max_retries = ConfigManager.get("llm.max_retries", 3)
        self.timeout = ConfigManager.get("llm.timeout", 30)
        self.temperature = ConfigManager.get("llm.temperature", 0.3)
        self.enable_cache = ConfigManager.get("llm.enable_cache", True)

        self._client = None
        self._budget_manager = TokenBudgetManager()
        self._init_client()

        from infra.prompt_manager import PromptManager

        self.prompt_mgr = PromptManager()
        self.system_prompt = (
            self.prompt_mgr.get_prompt("accounting_classifier") or "Default Prompt"
        )

    def _init_client(self):
        try:
            from openai import OpenAI

            self._client = OpenAI(
                base_url=self.base_url, api_key=self.api_key, timeout=self.timeout
            )
            log.info(f"LLM 客户端初始化成功: {self.base_url} | Model: {self.model}")
        except Exception as e:
            log.error(f"LLM 客户端初始化失败: {e}")

    def generate_response(
        self,
        prompt: str,
        system_role: str = "assistant",
        context_params: dict = None,
        images: list[str] = None,
    ) -> Dict[str, Any]:
        trace_id = TraceContext.get_trace_id()
        from infra.privacy_guard import PrivacyGuard

        guard = PrivacyGuard(role="LLM_PROXY")
        safe_prompt, was_masked = guard.sanitize_for_llm(prompt)

        sys_prompt = (
            self.prompt_mgr.render_prompt("accounting_classifier", context_params)
            if context_params
            else self.system_prompt
        )
        # Include image info in hash
        sys_hash_input = f"{sys_prompt}:{len(images) if images else 0}"
        sys_hash = hashlib.md5(sys_hash_input.encode()).hexdigest()[:8]

        current_model = self.fallback_model if self._using_fallback else self.model

        if self.enable_cache and not images:  # Skip cache for images for now
            cached = _response_cache.get(f"{sys_hash}:{safe_prompt}", current_model)
            if cached:
                self._budget_manager.record_cache_hit()
                return cached

        allowed, reason = self._budget_manager.check_budget()
        if not allowed or not self._client:
            if not self._using_fallback and self.fallback_model:
                log.warning(
                    f"主模型额度耗尽或不可用 ({reason})，正在尝试切换到备用模型: {self.fallback_model}"
                )
                self._using_fallback = True
            else:
                from infra.llm_mock import MockOpenManusLLM

                return MockOpenManusLLM().generate_response(
                    safe_prompt, system_role, images
                )

        current_model = self.fallback_model if self._using_fallback else self.model

        with TraceContext.start_span(
            "llm_generate_response", {"model": current_model}
        ) as span:
            start_time = time.time()

            # Construct messages with potential images
            if images:
                user_content = [{"type": "text", "text": safe_prompt}]
                for img_data in images:
                    # Format: data:image/jpeg;base64,{base64_string} or https://...
                    user_content.append(
                        {"type": "image_url", "image_url": {"url": img_data}}
                    )
                messages = [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_content},
                ]
            else:
                messages = [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": safe_prompt},
                ]

            try:
                result, usage = self._call_api_with_retry(
                    messages, model_override=current_model
                )
                if usage:
                    self._budget_manager.record_usage(
                        usage.get("prompt_tokens", 0),
                        usage.get("completion_tokens", 0),
                        model_name=current_model,
                    )

                response = {
                    "reasoning": f"LLM Analysis via {current_model}",
                    "result": {
                        "category": result.get("category", "待人工确认"),
                        "reason": result.get("reason", "Unknown"),
                    },
                    "confidence": float(result.get("confidence", 0.5)),
                    "latency_ms": int((time.time() - start_time) * 1000),
                    "model": current_model,
                    "from_cache": False,
                }
                if self.enable_cache:
                    _response_cache.set(
                        f"{sys_hash}:{safe_prompt}", current_model, response
                    )
                return response
            except Exception as e:
                log.error(f"模型 {current_model} 调用失败: {e}")
                if not self._using_fallback and self.fallback_model:
                    log.warning(
                        f"主模型调用异常，尝试切换到备用模型: {self.fallback_model}"
                    )
                    self._using_fallback = True
                    return self.generate_response(prompt, system_role, context_params)

                from infra.llm_mock import MockOpenManusLLM

                return MockOpenManusLLM().generate_response(safe_prompt, system_role)

    def _call_api_with_retry(self, messages: list, model_override: str = None):
        from agents.proxy_actor import ProxyActor

        proxy = ProxyActor()
        target_model = model_override or self.model
        for attempt in range(self.max_retries):
            try:
                response = proxy.send_llm_request(
                    client=self._client,
                    model=target_model,
                    messages=messages,
                    temperature=self.temperature,
                )
                content = response.choices[0].message.content
                usage = (
                    {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens,
                    }
                    if hasattr(response, "usage")
                    else {}
                )
                return self._parse_response(content), usage
            except Exception as e:
                if attempt < self.max_retries - 1:
                    time.sleep((2**attempt) + random.uniform(0, 1))
        raise Exception(f"Max retries exceeded for model {target_model}")

    def generate_embedding(self, text: str) -> list[float]:
        if not text:
            return []

        # Check cache first (embeddings are deterministic and expensive)
        text_hash = hashlib.md5(text.encode()).hexdigest()
        if self.enable_cache:
            cached = _response_cache.get(f"emb:{text_hash}", "embedding")
            if cached:
                return cached

        try:
            # Use separate model for embeddings if configured, else default to text-embedding-3-small
            emb_model = ConfigManager.get(
                "llm.embedding_model", "text-embedding-3-small"
            )

            with TraceContext.start_span("llm_embedding", {"model": emb_model}) as span:
                response = self._client.embeddings.create(input=text, model=emb_model)
                embedding = response.data[0].embedding

                if self.enable_cache:
                    _response_cache.set(f"emb:{text_hash}", "embedding", embedding)

                return embedding
        except Exception as e:
            log.error(f"Embedding generation failed: {e}")
            # Fallback to mock for stability in dev/test
            from infra.llm_mock import MockOpenManusLLM

            return MockOpenManusLLM().generate_embedding(text)

    def _parse_response(self, content: str) -> Dict[str, Any]:
        md_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        if md_match:
            try:
                return json.loads(md_match.group(1))
            except:
                pass
        brace_match = re.search(r"(\{.*\})", content, re.DOTALL)
        if brace_match:
            try:
                return json.loads(re.sub(r",\s*}", "}", brace_match.group(1)))
            except:
                pass
        return {
            "category": "待人工确认",
            "reason": "Failed to parse JSON",
            "confidence": 0.1,
        }
