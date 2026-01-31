from typing import Any, Dict, Type

class ConfigValidationError(Exception):
    """配置校验失败异常"""
    pass

def validate_config(config: Dict[str, Any]):
    """
    校验配置文件的核心字段及其类型
    """
    # 定义必须存在的键及其期望类型
    required_keys = {
        "path": {
            "logs": str,
            "db": str,
            "workspace": str
        },
        "intervals": {
            "daemon_poll": (int, float),
            "retry_backoff_base": (int, float)
        }
    }

    def check_recursive(conf_part, schema_part, prefix=""):
        for key, expected_type in schema_part.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if key not in conf_part:
                raise ConfigValidationError(f"缺少必需的配置项: {full_key}")
            
            val = conf_part[key]
            if isinstance(expected_type, dict):
                if not isinstance(val, dict):
                    raise ConfigValidationError(f"配置项 {full_key} 应该是对象类型")
                check_recursive(val, expected_type, full_key)
            else:
                if not isinstance(val, expected_type):
                    raise ConfigValidationError(f"配置项 {full_key} 类型错误 (期望 {expected_type}, 实际 {type(val)})")

    check_recursive(config, required_keys)
    return True
