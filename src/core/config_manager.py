import yaml
import os
import threading
from typing import Any, Dict, Optional, Type, TypeVar, Union
from project_paths import get_path
from config_validation import validate_config

T = TypeVar('T')


class ConfigSchema:
    """
    [Optimization Iteration 4] 配置项类型定义
    定义配置项的预期类型，用于运行时类型校验
    """
    SCHEMA: Dict[str, Type] = {
        # 路径配置
        "path.db": str,
        "path.logs": str,
        "path.input": str,
        "path.rules": str,
        "path.workspace": str,

        # 时间间隔配置
        "intervals.daemon_poll": (int, float),
        "intervals.collector_scan": (int, float),
        "intervals.match_engine_loop": (int, float),
        "intervals.retry_backoff_base": (int, float),
        "intervals.health_timeout": (int, float),

        # 阈值配置
        "threshold.confidence_high": float,
        "threshold.confidence_low": float,
        "threshold.token_budget_per_task": float,
        "threshold.semantic_match_min": float,
        "threshold.semantic_match_high": float,
        "threshold.capex_amount": (int, float),
        "threshold.micro_payment_waiver": (int, float),
        "threshold.risk_score_reject": float,
        "threshold.risk_score_upgrade": float,
        "threshold.price_outlier_factor": float,

        # 数据库配置
        "db.retry_count": int,
        "db.retry_delay": float,
        "db.busy_timeout": int,
        "db.journal_mode": str,

        # LLM 配置
        "llm.type": str,
        "llm.base_url": str,
        "llm.api_key": str,
        "llm.model": str,
        "llm.max_retries": int,
        "llm.timeout": (int, float),
        "llm.temperature": float,
        "llm.enable_cache": bool,
        "llm.daily_budget_usd": float,
        "llm.monthly_budget_usd": float,

        # 审计配置
        "audit.outlier_factor": float,
        "audit.force_manual_amount": (int, float),
        "audit.auto_approve_threshold": float,

        # 采集器配置
        "collector.worker_threads": int,
        "collector.initial_scan_enabled": bool,

        # 企业配置
        "enterprise.sector": str,
    }

    @classmethod
    def get_expected_type(cls, key_path: str) -> Optional[Type]:
        """获取配置项的预期类型"""
        return cls.SCHEMA.get(key_path)

    @classmethod
    def validate_type(cls, key_path: str, value: Any) -> bool:
        """验证配置值类型是否正确"""
        expected = cls.get_expected_type(key_path)
        if expected is None:
            return True  # 未定义的配置项不做校验

        if isinstance(expected, tuple):
            return isinstance(value, expected)
        return isinstance(value, expected)


class ConfigManager:
    """
    [Optimization Iteration 4] 增强型配置管理器
    - 类型安全的配置获取
    - 配置值自动类型转换
    - 配置访问统计
    """
    _config = None
    _last_loaded = 0
    _lock = threading.Lock()
    _access_stats: Dict[str, int] = {}  # 配置访问统计

    @classmethod
    def load(cls, force=False):
        with cls._lock:
            path = get_path("config", "settings.yaml")

            # 1. 检查是否需要重新加载 (热加载机制)
            if not force and cls._config and os.path.exists(path):
                if os.path.getmtime(path) <= cls._last_loaded:
                    return cls._config

            # 2. 默认配置
            defaults = {
                "path": {
                    "db": get_path("ledger_alpha.db"),
                    "logs": get_path("logs"),
                    "input": get_path("workspace", "input"),
                    "rules": get_path("src", "accounting_rules.yaml"),
                    "workspace": get_path("workspace")
                },
                "intervals": {
                    "daemon_poll": 5,
                    "retry_backoff_base": 2,
                    "health_timeout": 60
                },
                "threshold": {"confidence_high": 0.95}
            }

            # 3. 加载用户配置
            user_config = {}
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    user_config = yaml.safe_load(f) or {}

                # 自动将 path 下的相对路径转换为绝对路径
                if "path" in user_config:
                    for k, v in user_config["path"].items():
                        if isinstance(v, str) and not os.path.isabs(v):
                            user_config["path"][k] = get_path(v)

                cls._last_loaded = os.path.getmtime(path)

            # 4. 深度合并默认配置与用户配置
            final_config = cls._deep_merge(defaults, user_config)

            # 5. 环境变量覆盖
            for env_key, env_val in os.environ.items():
                if env_key.startswith("LEDGER_"):
                    cls._apply_env_override(final_config, env_key, env_val)

            # 6. 配置强校验
            validate_config(final_config)

            cls._config = final_config
            return cls._config

    @classmethod
    def _deep_merge(cls, base, update):
        for k, v in update.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                base[k] = cls._deep_merge(base[k], v)
            else:
                base[k] = v
        return base

    @classmethod
    def _apply_env_override(cls, config, env_key, env_val):
        # LEDGER_PATH_DB -> path.db
        parts = env_key[7:].lower().split('_')
        curr = config
        for part in parts[:-1]:
            if part not in curr: curr[part] = {}
            curr = curr[part]

        # 尝试自动转换类型
        try:
            if env_val.lower() in ('true', 'false'):
                curr[parts[-1]] = env_val.lower() == 'true'
            elif '.' in env_val:
                curr[parts[-1]] = float(env_val)
            else:
                curr[parts[-1]] = int(env_val)
        except ValueError:
            curr[parts[-1]] = env_val

    @classmethod
    def get(cls, key_path: str, default: T = None, expected_type: Type[T] = None) -> T:
        """
        [Optimization Iteration 4] 类型安全的配置获取

        Args:
            key_path: 配置路径，如 "llm.timeout"
            default: 默认值
            expected_type: 期望的返回类型，用于自动类型转换

        Returns:
            配置值，如果类型不匹配会尝试转换
        """
        import time
        if time.time() - cls._last_loaded > 1.0:
            cls.load()

        # 记录访问统计
        cls._access_stats[key_path] = cls._access_stats.get(key_path, 0) + 1

        keys = key_path.split('.')
        val = cls._config
        try:
            for k in keys:
                val = val[k]
        except (KeyError, TypeError):
            return default

        # [Optimization Iteration 4] 类型校验与转换
        if expected_type is not None:
            val = cls._convert_type(val, expected_type, key_path)
        elif not ConfigSchema.validate_type(key_path, val):
            expected = ConfigSchema.get_expected_type(key_path)
            if expected:
                val = cls._convert_type(val, expected, key_path)

        return val

    @classmethod
    def _convert_type(cls, value: Any, target_type: Union[Type, tuple], key_path: str) -> Any:
        """尝试将值转换为目标类型"""
        if isinstance(target_type, tuple):
            target_type = target_type[0]  # 使用第一个类型作为转换目标

        if isinstance(value, target_type):
            return value

        try:
            if target_type == bool:
                if isinstance(value, str):
                    return value.lower() in ('true', '1', 'yes', 'on')
                return bool(value)
            elif target_type == int:
                return int(float(value))
            elif target_type == float:
                return float(value)
            elif target_type == str:
                return str(value)
            else:
                return value
        except (ValueError, TypeError):
            from logger import get_logger
            get_logger("ConfigManager").warning(
                f"配置类型转换失败: {key_path} = {value} (期望 {target_type.__name__})"
            )
            return value

    @classmethod
    def get_int(cls, key_path: str, default: int = 0) -> int:
        """获取整数类型配置"""
        return cls.get(key_path, default, int)

    @classmethod
    def get_float(cls, key_path: str, default: float = 0.0) -> float:
        """获取浮点类型配置"""
        return cls.get(key_path, default, float)

    @classmethod
    def get_bool(cls, key_path: str, default: bool = False) -> bool:
        """获取布尔类型配置"""
        return cls.get(key_path, default, bool)

    @classmethod
    def get_str(cls, key_path: str, default: str = "") -> str:
        """获取字符串类型配置"""
        return cls.get(key_path, default, str)

    @classmethod
    def get_access_stats(cls) -> Dict[str, int]:
        """获取配置访问统计"""
        return cls._access_stats.copy()
