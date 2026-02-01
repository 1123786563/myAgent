import threading
import time
import hashlib
import re
from core.config_manager import ConfigManager
from infra.logger import get_logger

log = get_logger("LLMResponseCache")

class LLMResponseCache:
    """
    [Optimization Iteration 3] LLM 响应缓存
    """
    def __init__(self, max_size: int = 500, ttl_seconds: int = 3600):
        self.cache = {}
        self.access_times = {}
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()

    def _generate_key(self, prompt: str, model: str) -> str:
        normalized_prompt = re.sub(r'\s+', '', prompt).lower()
        content = f"{model}:{normalized_prompt}"
        return hashlib.md5(content.encode()).hexdigest()

    def get(self, prompt: str, model: str) -> dict:
        key = self._generate_key(prompt, model)
        with self._lock:
            if key in self.cache:
                entry = self.cache[key]
                if time.time() - entry["timestamp"] < self.ttl_seconds:
                    self.access_times[key] = time.time()
                    return entry["response"]
                else:
                    del self.cache[key]
                    if key in self.access_times:
                        del self.access_times[key]
        return None

    def set(self, prompt: str, model: str, response: dict):
        key = self._generate_key(prompt, model)
        with self._lock:
            if len(self.cache) >= self.max_size:
                oldest_key = min(self.access_times, key=self.access_times.get)
                del self.cache[oldest_key]
                del self.access_times[oldest_key]
            self.cache[key] = {
                "response": response,
                "timestamp": time.time()
            }
            self.access_times[key] = time.time()

_response_cache = LLMResponseCache(
    max_size=ConfigManager.get("llm.cache_max_size", 500),
    ttl_seconds=ConfigManager.get("llm.cache_ttl_seconds", 3600)
)
