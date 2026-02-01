import sqlite3
import threading
from decimal import Decimal
from typing import Dict, Any

def adapt_decimal(d):
    return str(d)

def convert_decimal(s):
    return Decimal(s.decode('utf-8'))

sqlite3.register_adapter(Decimal, adapt_decimal)
sqlite3.register_converter("DECIMAL", convert_decimal)

class DBMetrics:
    """
    [Optimization Iteration 4] 数据库操作指标收集器
    """
    _lock = threading.Lock()
    _stats = {
        "total_transactions": 0,
        "successful_transactions": 0,
        "failed_transactions": 0,
        "retried_transactions": 0,
        "slow_transactions": 0,
        "total_duration_ms": 0,
        "connections_created": 0,
        "connections_reused": 0,
        "health_checks": 0,
        "health_check_failures": 0
    }

    @classmethod
    def record_transaction(cls, success: bool, duration_ms: float, retries: int = 0, slow: bool = False):
        with cls._lock:
            cls._stats["total_transactions"] += 1
            cls._stats["total_duration_ms"] += duration_ms
            if success:
                cls._stats["successful_transactions"] += 1
            else:
                cls._stats["failed_transactions"] += 1
            if retries > 0:
                cls._stats["retried_transactions"] += 1
            if slow:
                cls._stats["slow_transactions"] += 1

    @classmethod
    def record_connection(cls, reused: bool):
        with cls._lock:
            if reused:
                cls._stats["connections_reused"] += 1
            else:
                cls._stats["connections_created"] += 1

    @classmethod
    def record_health_check(cls, success: bool):
        with cls._lock:
            cls._stats["health_checks"] += 1
            if not success:
                cls._stats["health_check_failures"] += 1

    @classmethod
    def get_stats(cls) -> Dict[str, Any]:
        with cls._lock:
            stats = cls._stats.copy()
        if stats["total_transactions"] > 0:
            stats["avg_duration_ms"] = round(
                stats["total_duration_ms"] / stats["total_transactions"], 2
            )
            stats["success_rate"] = round(
                stats["successful_transactions"] / stats["total_transactions"] * 100, 2
            )
        return stats
