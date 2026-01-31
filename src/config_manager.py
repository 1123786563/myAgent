import yaml
import os
import threading
from project_paths import get_path
from config_validation import validate_config

class ConfigManager:
    _config = None
    _last_loaded = 0
    _lock = threading.Lock()

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
    def get(cls, key_path, default=None):
        cls.load() # 触发潜在的热加载检查
        
        keys = key_path.split('.')
        val = cls._config
        try:
            for k in keys:
                val = val[k]
            return val
        except (KeyError, TypeError):
            return default
