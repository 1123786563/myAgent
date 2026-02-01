import threading
import time
import random
from core.config_manager import ConfigManager
from infra.logger import get_logger

log = get_logger("TokenBudgetManager")

class TokenBudgetManager:
    """
    [Optimization Iteration 3] Token 用量统计与预算控制
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

        self.daily_budget_usd = ConfigManager.get("llm.daily_budget_usd", 10.0)
        self.monthly_budget_usd = ConfigManager.get("llm.monthly_budget_usd", 200.0)

        self.input_price_per_1k = ConfigManager.get("llm.input_price_per_1k", 0.0001)
        self.output_price_per_1k = ConfigManager.get("llm.output_price_per_1k", 0.0002)

    def _maybe_reset_counters(self):
        today = time.strftime("%Y-%m-%d")
        month = time.strftime("%Y-%m")

        if today != self.last_reset_day:
            self.daily_tokens = 0
            self.daily_cost_usd = 0.0
            self.last_reset_day = today

        if month != self.last_reset_month:
            self.monthly_tokens = 0
            self.monthly_cost_usd = 0.0
            self.last_reset_month = month

    def check_budget(self) -> tuple:
        self._maybe_reset_counters()
        if self.daily_cost_usd >= self.daily_budget_usd:
            return False, f"日预算已用尽 (${self.daily_cost_usd:.2f} >= ${self.daily_budget_usd:.2f})"
        if self.monthly_cost_usd >= self.monthly_budget_usd:
            return False, f"月预算已用尽 (${self.monthly_cost_usd:.2f} >= ${self.monthly_budget_usd:.2f})"
        return True, "OK"

    def record_usage(self, input_tokens: int, output_tokens: int):
        self._maybe_reset_counters()
        total_tokens = input_tokens + output_tokens
        try:
            if not hasattr(self, '_last_rate') or random.random() < 0.01:
                model_name = str(ConfigManager.get("llm.model", "default")).lower()
                price_map = {
                    "gpt-4o-mini": {"in": 0.00015, "out": 0.0006},
                    "gpt-4o": {"in": 0.005, "out": 0.015},
                    "o1-": {"in": 0.015, "out": 0.06},
                    "claude-3-5": {"in": 0.003, "out": 0.015},
                    "gemini-3-flash": {"in": 0.0001, "out": 0.0003},
                    "default": {"in": self.input_price_per_1k, "out": self.output_price_per_1k}
                }
                matched_cfg = price_map["default"]
                sorted_keys = sorted([k for k in price_map.keys() if k != "default"], key=len, reverse=True)
                for key in sorted_keys:
                    if key in model_name:
                        matched_cfg = price_map[key]
                        break
                with self._lock:
                    self._last_rate = matched_cfg
                    self._current_model = model_name
            else:
                with self._lock:
                    matched_cfg = self._last_rate
                    model_name = self._current_model

            cost = (input_tokens / 1000 * matched_cfg["in"] +
                    output_tokens / 1000 * matched_cfg["out"])

            with self._lock:
                self.daily_tokens += total_tokens
                self.daily_cost_usd += cost
                self.monthly_tokens += total_tokens
                self.monthly_cost_usd += cost
                self.request_count += 1
            log.debug(f"Token 使用: +{total_tokens} ({model_name}), 成本: +${cost:.4f}")
        except Exception as e:
            log.error(f"计费引擎异常: {e}")

    def record_cache_hit(self):
        with self._lock:
            self.cache_hits += 1

    def get_stats(self) -> dict:
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
