import abc
import json
import time
import random
import os
import hashlib
import threading
import re
from typing import Optional, Tuple, Dict, Any
from logger import get_logger
from project_paths import get_path
from config_manager import ConfigManager
from trace_context import TraceContext

log = get_logger("LLMConnector")


class TokenBudgetManager:
    """
    [Optimization Iteration 3] Token 用量统计与预算控制
    防止 LLM 成本失控，支持日/月预算限制
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init_stats()
        return cls._instance

    def _init_stats(self):
        self.daily_tokens = 0
        self.daily_cost_usd = 0.0
        self.monthly_tokens = 0
        self.monthly_cost_usd = 0.0
        self.request_count = 0
        self.cache_hits = 0
        self.last_reset_day = time.strftime("%Y-%m-%d")
        self.last_reset_month = time.strftime("%Y-%m")

        # 从配置加载预算限制
        self.daily_budget_usd = ConfigManager.get("llm.daily_budget_usd", 10.0)
        self.monthly_budget_usd = ConfigManager.get("llm.monthly_budget_usd", 200.0)

        # Token 价格 (每 1K tokens)
        self.input_price_per_1k = ConfigManager.get("llm.input_price_per_1k", 0.0001)
        self.output_price_per_1k = ConfigManager.get("llm.output_price_per_1k", 0.0002)

    def _maybe_reset_counters(self):
        """检查并重置日/月计数器"""
        today = time.strftime("%Y-%m-%d")
        month = time.strftime("%Y-%m")

        if today != self.last_reset_day:
            log.info(f"Token 日统计重置: 昨日消耗 {self.daily_tokens} tokens, ${self.daily_cost_usd:.4f}")
            self.daily_tokens = 0
            self.daily_cost_usd = 0.0
            self.last_reset_day = today

        if month != self.last_reset_month:
            log.info(f"Token 月统计重置: 上月消耗 {self.monthly_tokens} tokens, ${self.monthly_cost_usd:.4f}")
            self.monthly_tokens = 0
            self.monthly_cost_usd = 0.0
            self.last_reset_month = month

    def check_budget(self) -> tuple:
        """检查预算是否超限，返回 (是否允许, 原因)"""
        self._maybe_reset_counters()

        if self.daily_cost_usd >= self.daily_budget_usd:
            return False, f"日预算已用尽 (${self.daily_cost_usd:.2f} >= ${self.daily_budget_usd:.2f})"

        if self.monthly_cost_usd >= self.monthly_budget_usd:
            return False, f"月预算已用尽 (${self.monthly_cost_usd:.2f} >= ${self.monthly_budget_usd:.2f})"

        return True, "OK"

    def record_usage(self, input_tokens: int, output_tokens: int):
        """记录 Token 使用量"""
        self._maybe_reset_counters()

        total_tokens = input_tokens + output_tokens
        
        # [Round 25/27/28/32/33/38/42/46] 性能与安全双修
        try:
            # 引入更严谨的模型名探测
            if not hasattr(self, '_last_rate') or random.random() < 0.01:
                from config_manager import ConfigManager
                model_name = str(ConfigManager.get("llm.model", "default")).lower()
                
                price_map = {
                    "gpt-4o-mini": {"in": 0.00015, "out": 0.0006},
                    "gpt-4o": {"in": 0.005, "out": 0.015},
                    "o1-": {"in": 0.015, "out": 0.06}, # 支持 o1-preview, o1-mini
                    "claude-3-5": {"in": 0.003, "out": 0.015},
                    "gemini-3-flash": {"in": 0.0001, "out": 0.0003},
                    "default": {"in": self.input_price_per_1k, "out": self.output_price_per_1k}
                }
                
                # [Round 46] 增加权重路由逻辑
                matched_cfg = price_map["default"]
                sorted_keys = sorted([k for k in price_map.keys() if k != "default"], key=len, reverse=True)
                for key in sorted_keys:
                    if key in model_name: # 变 startswith 为更通用的包含判定
                        matched_cfg = price_map[key]
                        break
                
                with self._lock:
                    self._last_rate = matched_cfg
                    self._current_model = model_name
            else:
                with self._lock:
                    matched_cfg = self._last_rate
                    model_name = self._current_model

            # ...

            cost = (input_tokens / 1000 * matched_cfg["in"] +
                    output_tokens / 1000 * matched_cfg["out"])

            with self._lock:
                self.daily_tokens += total_tokens
                self.daily_cost_usd += cost
                self.monthly_tokens += total_tokens
                self.monthly_cost_usd += cost
                self.request_count += 1
                self.last_request_cost = cost

            log.debug(f"Token 使用: +{total_tokens} ({model_name}), 成本: +${cost:.4f}")
        except Exception as e:
            # [Round 42] 容错保护：计费失败不应阻断业务流
            log.error(f"计费引擎异常: {e}")

    def record_cache_hit(self):
        """记录缓存命中"""
        with self._lock:
            self.cache_hits += 1

    def get_stats(self) -> dict:
        """获取统计信息"""
        self._maybe_reset_counters()
        return {
            "daily_tokens": self.daily_tokens,
            "daily_cost_usd": round(self.daily_cost_usd, 4),
            "monthly_tokens": self.monthly_tokens,
            "monthly_cost_usd": round(self.monthly_cost_usd, 4),
            "request_count": self.request_count,
            "cache_hits": self.cache_hits,
            "cache_hit_rate": round(self.cache_hits / max(1, self.request_count + self.cache_hits) * 100, 1)
        }


class LLMResponseCache:
    """
    [Optimization Iteration 3] LLM 响应缓存
    相同查询避免重复调用，节省成本
    """
    def __init__(self, max_size: int = 500, ttl_seconds: int = 3600):
        self.cache = {}
        self.access_times = {}
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()

    def _generate_key(self, prompt: str, model: str) -> str:
        """
        [Optimization Round 8] 归一化缓存键生成
        通过去除空白符、转换为小写等方式，提高缓存命中率
        """
        # 归一化处理：去除所有空白符并转小写
        normalized_prompt = re.sub(r'\s+', '', prompt).lower()
        content = f"{model}:{normalized_prompt}"
        return hashlib.md5(content.encode()).hexdigest()

    def get(self, prompt: str, model: str) -> dict:
        """获取缓存的响应"""
        key = self._generate_key(prompt, model)

        with self._lock:
            if key in self.cache:
                entry = self.cache[key]
                # 检查 TTL
                if time.time() - entry["timestamp"] < self.ttl_seconds:
                    self.access_times[key] = time.time()
                    log.debug(f"LLM 缓存命中: {key[:8]}...")
                    return entry["response"]
                else:
                    # 过期，删除
                    del self.cache[key]
                    if key in self.access_times:
                        del self.access_times[key]

        return None

    def set(self, prompt: str, model: str, response: dict):
        """存储响应到缓存"""
        key = self._generate_key(prompt, model)

        with self._lock:
            # LRU 淘汰
            if len(self.cache) >= self.max_size:
                oldest_key = min(self.access_times, key=self.access_times.get)
                del self.cache[oldest_key]
                del self.access_times[oldest_key]
                log.debug(f"LLM 缓存淘汰: {oldest_key[:8]}...")

            self.cache[key] = {
                "response": response,
                "timestamp": time.time()
            }
            self.access_times[key] = time.time()

    def clear(self):
        """清空缓存"""
        with self._lock:
            self.cache.clear()
            self.access_times.clear()
        log.info("LLM 响应缓存已清空")


# 全局缓存实例
_response_cache = LLMResponseCache(
    max_size=ConfigManager.get("llm.cache_max_size", 500),
    ttl_seconds=ConfigManager.get("llm.cache_ttl_seconds", 3600)
)


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


class OpenAICompatibleLLM(BaseLLM):
    """
    [Optimization Iteration 2] 真实 LLM API 接入
    [Optimization Iteration 3] 集成 Token 预算管理与响应缓存
    支持 OpenAI 兼容 API (包括本地部署的模型服务)
    """

    def __init__(self):
        self.base_url = ConfigManager.get("llm.base_url", "http://127.0.0.1:8045/v1")
        self.api_key = ConfigManager.get("llm.api_key")
        self.model = ConfigManager.get("llm.model", "gemini-3-flash")
        self.max_retries = ConfigManager.get("llm.max_retries", 3)
        self.timeout = ConfigManager.get("llm.timeout", 30)
        self.temperature = ConfigManager.get("llm.temperature", 0.3)
        self.enable_cache = ConfigManager.get("llm.enable_cache", True)

        self._client = None
        self._budget_manager = TokenBudgetManager()
        self._init_client()

        # [Optimization Round 4] 使用外部 Prompt 管理器
        from prompt_manager import PromptManager
        self.prompt_mgr = PromptManager()
        self.system_prompt = self.prompt_mgr.get_prompt("accounting_classifier") or "Default Prompt"

    def _init_client(self):
        """初始化 OpenAI 客户端"""
        try:
            from openai import OpenAI
            self._client = OpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                timeout=self.timeout
            )
            log.info(f"LLM 客户端初始化成功: {self.base_url} | Model: {self.model}")
        except ImportError:
            log.error("未安装 openai 库，请执行: pip install openai")
            self._client = None
        except Exception as e:
            log.error(f"LLM 客户端初始化失败: {e}")
            self._client = None

    def _call_api_with_retry(self, messages: list) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        [Optimization Iteration 5] 带重试机制和分布式追踪的 API 调用
        [Optimization Round 3] 集成 ProxyActor 强制出口检查
        返回 (解析结果, usage信息)
        """
        last_error = None
        trace_id = TraceContext.get_trace_id()
        
        # 初始化强制代理
        from proxy_actor import ProxyActor
        proxy = ProxyActor()

        for attempt in range(self.max_retries):
            with TraceContext.start_span("llm_api_call", {
                "attempt": attempt + 1,
                "model": self.model,
                "base_url": self.base_url
            }) as span:
                try:
                    # 使用代理发送请求，而不是直接调用 client
                    response = proxy.send_llm_request(
                        client=self._client,
                        model=self.model,
                        messages=messages,
                        temperature=self.temperature,
                        max_tokens=500
                    )

                    content = response.choices[0].message.content
                    log.debug(f"LLM 原始响应: {content[:200]}...", extra={"trace_id": trace_id})

                    # 提取 usage 信息
                    usage = {}
                    if hasattr(response, 'usage') and response.usage:
                        usage = {
                            "prompt_tokens": response.usage.prompt_tokens,
                            "completion_tokens": response.usage.completion_tokens,
                            "total_tokens": response.usage.total_tokens
                        }
                        span["attributes"]["tokens"] = usage.get("total_tokens", 0)

                    # 尝试解析 JSON 响应
                    parsed = self._parse_response(content)
                    span["attributes"]["success"] = True
                    return parsed, usage

                except Exception as e:
                    last_error = e
                    span["attributes"]["error"] = str(e)
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    log.warning(
                        f"LLM API 调用失败 (尝试 {attempt + 1}/{self.max_retries}): {e}",
                        extra={"trace_id": trace_id}
                    )

                    if attempt < self.max_retries - 1:
                        log.info(f"等待 {wait_time:.1f}s 后重试...", extra={"trace_id": trace_id})
                        time.sleep(wait_time)

        raise last_error

    def _parse_response(self, content: str) -> Dict[str, Any]:
        """
        [Optimization Round 4] 极致鲁棒的 JSON 解析
        支持 Markdown、混合文本、转义字符及非法尾随字符处理
        """
        if not content or not isinstance(content, str):
            return {"category": "待核定", "reason": "Empty LLM response", "confidence": 0.0}

        # 1. 尝试提取 Markdown JSON 块
        md_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
        if md_match:
            candidate = md_match.group(1)
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

        # 2. 尝试正则提取第一个 { 到 最后一个 } 之间的内容
        brace_match = re.search(r'(\{.*\})', content, re.DOTALL)
        if brace_match:
            candidate = brace_match.group(1)
            try:
                # 预处理：移除潜在的尾随逗号 (common in LLM output)
                candidate = re.sub(r',\s*}', '}', candidate)
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

        # 3. 实在不行，尝试按行提取关键字段 (Heuristic Fallback)
        log.warning(f"JSON 解析彻底失败，执行启发式提取: {content[:100]}...")
        extracted = {}
        for key in ["category", "reason"]:
            match = re.search(rf'"{key}"\s*:\s*"([^"]+)"', content)
            if match:
                extracted[key] = match.group(1)
        
        if extracted.get("category"):
            extracted["confidence"] = 0.4
            return extracted

        return {
            "category": "待人工确认",
            "reason": f"无法解析响应结构: {content[:50]}",
            "confidence": 0.1
        }

    def generate_response(self, prompt: str, system_role: str = "assistant", context_params: dict = None) -> Dict[str, Any]:
        """
        [Optimization Round 20] 增强的 LLM 调用方法，支持动态提示词参数渲染
        """
        trace_id = TraceContext.get_trace_id()

        # 0. 隐私脱敏处理 (Privacy Guard)
        from privacy_guard import PrivacyGuard
        guard = PrivacyGuard(role="LLM_PROXY")
        safe_prompt, was_masked = guard.sanitize_for_llm(prompt)
        if was_masked:
            log.info(f"LLM 请求已脱敏 | TraceID={trace_id}")

        # [Round 20] 动态渲染系统提示词
        if context_params:
            sys_prompt = self.prompt_mgr.render_prompt("accounting_classifier", context_params) or self.system_prompt
        else:
            sys_prompt = self.system_prompt

        # 1. 检查缓存
        # [Round 20] 缓存键包含系统提示词哈希，确保动态参数变化时缓存正确失效
        sys_hash = hashlib.md5(sys_prompt.encode()).hexdigest()[:8]
        if self.enable_cache:
            cached = _response_cache.get(f"{sys_hash}:{safe_prompt}", self.model)
            if cached:
                self._budget_manager.record_cache_hit()
                cached["from_cache"] = True
                log.info(f"LLM 缓存命中，跳过 API 调用", extra={"trace_id": trace_id})
                return cached

        # 2. 检查预算
        allowed, reason = self._budget_manager.check_budget()
        if not allowed:
            log.warning(f"LLM 预算超限: {reason}，降级到 Mock 模式", extra={"trace_id": trace_id})
            return MockOpenManusLLM().generate_response(safe_prompt, system_role)

        # 3. 检查客户端
        if not self._client:
            log.error("LLM 客户端未初始化，回退到 Mock 模式", extra={"trace_id": trace_id})
            return MockOpenManusLLM().generate_response(safe_prompt, system_role)

        # 4. 使用 Span 包裹整个 LLM 调用流程
        with TraceContext.start_span("llm_generate_response", {
            "model": self.model,
            "prompt_length": len(safe_prompt)
        }) as span:
            start_time = time.time()
            log.info(f"调用 LLM API: {safe_prompt[:50]}...", extra={"trace_id": trace_id})

            messages = [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": safe_prompt}
            ]

            try:
                result, usage = self._call_api_with_retry(messages)
                elapsed = time.time() - start_time

                # 5. 记录 Token 使用量
                if usage:
                    self._budget_manager.record_usage(
                        usage.get("prompt_tokens", 0),
                        usage.get("completion_tokens", 0)
                    )
                    span["attributes"]["total_tokens"] = usage.get("total_tokens", 0)

                # 标准化响应格式
                response = {
                    "reasoning": f"LLM Analysis via {self.model}",
                    "result": {
                        "category": result.get("category", "待人工确认"),
                        "reason": result.get("reason", "Unknown")
                    },
                    "confidence": float(result.get("confidence", 0.5)),
                    "latency_ms": int(elapsed * 1000),
                    "model": self.model,
                    "from_cache": False
                }

                span["attributes"]["latency_ms"] = response["latency_ms"]
                span["attributes"]["confidence"] = response["confidence"]

                # 6. 存入缓存
                if self.enable_cache:
                    _response_cache.set(f"{sys_hash}:{safe_prompt}", self.model, response)

                log.info(
                    f"LLM 响应成功: {response['result']['category']} (Conf: {response['confidence']:.2f}, Latency: {response['latency_ms']}ms)",
                    extra={"trace_id": trace_id}
                )
                return response

            except Exception as e:
                elapsed = time.time() - start_time
                span["attributes"]["error"] = str(e)
                log.error(f"LLM API 调用最终失败 ({elapsed:.1f}s): {e}", extra={"trace_id": trace_id})

                # 降级到 Mock 模式
                log.warning("降级到 Mock 模式进行分类...", extra={"trace_id": trace_id})
                return MockOpenManusLLM().generate_response(safe_prompt, system_role)


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
    """
    [Optimization Iteration 2] 增强的 LLM 工厂
    支持多种 LLM 后端切换
    """
    _instances = {}

    @staticmethod
    def get_llm(llm_type: str = None) -> BaseLLM:
        """
        获取 LLM 实例 (单例模式)

        Args:
            llm_type: LLM 类型，可选值:
                - "OPENAI": 真实 OpenAI 兼容 API
                - "MOCK": 模拟 LLM (用于测试)
                - None: 从配置文件读取
        """
        if llm_type is None:
            llm_type = ConfigManager.get("llm.type", "OPENAI")

        llm_type = llm_type.upper()

        # 单例缓存
        if llm_type in LLMFactory._instances:
            return LLMFactory._instances[llm_type]

        if llm_type == "OPENAI":
            instance = OpenAICompatibleLLM()
        elif llm_type == "MOCK":
            instance = MockOpenManusLLM()
        else:
            log.warning(f"未知的 LLM 类型 '{llm_type}'，使用 Mock 模式")
            instance = MockOpenManusLLM()

        LLMFactory._instances[llm_type] = instance
        return instance

    @staticmethod
    def reset():
        """清除缓存的实例 (用于测试或配置变更后重新初始化)"""
        LLMFactory._instances.clear()
        log.info("LLM 实例缓存已清除")
