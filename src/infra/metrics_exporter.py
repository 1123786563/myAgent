"""
[Optimization Iteration 6] Prometheus 指标导出器

提供系统运行指标的 Prometheus 格式导出，支持监控系统集成。
"""

import time
import threading
from typing import Dict, Any, List
from http.server import HTTPServer, BaseHTTPRequestHandler
from infra.logger import get_logger
from core.config_manager import ConfigManager

log = get_logger("MetricsExporter")


class MetricsCollector:
    """
    系统指标收集器 - 聚合各模块的运行指标
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init()
        return cls._instance

    def _init(self):
        self._metrics: Dict[str, Dict[str, Any]] = {}
        self._counters: Dict[str, float] = {}
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = {}
        self._start_time = time.time()

    def counter_inc(self, name: str, value: float = 1.0, labels: Dict[str, str] = None):
        """增加计数器"""
        key = self._make_key(name, labels)
        with self._lock:
            self._counters[key] = self._counters.get(key, 0) + value

    def gauge_set(self, name: str, value: float, labels: Dict[str, str] = None):
        """设置仪表盘值"""
        key = self._make_key(name, labels)
        with self._lock:
            self._gauges[key] = value

    def histogram_observe(self, name: str, value: float, labels: Dict[str, str] = None):
        """记录直方图观测值"""
        key = self._make_key(name, labels)
        with self._lock:
            if key not in self._histograms:
                self._histograms[key] = []
            self._histograms[key].append(value)
            # 保留最近 1000 个观测值
            if len(self._histograms[key]) > 1000:
                self._histograms[key] = self._histograms[key][-1000:]

    def _make_key(self, name: str, labels: Dict[str, str] = None) -> str:
        """生成带标签的指标键"""
        if not labels:
            return name
        label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"

    def collect_system_metrics(self):
        """收集系统级指标"""
        import os

        # 进程运行时间
        self.gauge_set("ledger_uptime_seconds", time.time() - self._start_time)

        # 进程 ID
        self.gauge_set("ledger_process_pid", os.getpid())

    def collect_db_metrics(self):
        """收集数据库指标"""
        try:
            from core.db_helper import DBHelper, DBMetrics
            stats = DBMetrics.get_stats()

            self.gauge_set("ledger_db_transactions_total", stats.get("total_transactions", 0))
            self.gauge_set("ledger_db_transactions_success", stats.get("successful_transactions", 0))
            self.gauge_set("ledger_db_transactions_failed", stats.get("failed_transactions", 0))
            self.gauge_set("ledger_db_transactions_slow", stats.get("slow_transactions", 0))
            self.gauge_set("ledger_db_avg_duration_ms", stats.get("avg_duration_ms", 0))
            self.gauge_set("ledger_db_success_rate", stats.get("success_rate", 0))
            self.gauge_set("ledger_db_connections_created", stats.get("connections_created", 0))
            self.gauge_set("ledger_db_connections_reused", stats.get("connections_reused", 0))
        except Exception as e:
            log.debug(f"收集数据库指标失败: {e}")

    def collect_llm_metrics(self):
        """收集 LLM 指标"""
        try:
            from infra.llm_connector import TokenBudgetManager
            stats = TokenBudgetManager().get_stats()

            self.gauge_set("ledger_llm_daily_tokens", stats.get("daily_tokens", 0))
            self.gauge_set("ledger_llm_daily_cost_usd", stats.get("daily_cost_usd", 0))
            self.gauge_set("ledger_llm_monthly_tokens", stats.get("monthly_tokens", 0))
            self.gauge_set("ledger_llm_monthly_cost_usd", stats.get("monthly_cost_usd", 0))
            self.gauge_set("ledger_llm_request_count", stats.get("request_count", 0))
            self.gauge_set("ledger_llm_cache_hits", stats.get("cache_hits", 0))
            self.gauge_set("ledger_llm_cache_hit_rate", stats.get("cache_hit_rate", 0))
        except Exception as e:
            log.debug(f"收集 LLM 指标失败: {e}")

    def collect_trace_metrics(self):
        """收集追踪指标"""
        try:
            from infra.trace_context import TraceContext
            stats = TraceContext.get_stats()

            self.gauge_set("ledger_traces_created", stats.get("traces_created", 0))
            self.gauge_set("ledger_spans_created", stats.get("spans_created", 0))
            self.gauge_set("ledger_trace_avg_duration_ms", stats.get("avg_duration_ms", 0))
        except Exception as e:
            log.debug(f"收集追踪指标失败: {e}")

    def get_prometheus_output(self) -> str:
        """生成 Prometheus 格式的指标输出"""
        # 先收集最新指标
        self.collect_system_metrics()
        self.collect_db_metrics()
        self.collect_llm_metrics()
        self.collect_trace_metrics()

        lines = []
        lines.append("# HELP ledger_uptime_seconds Time since service start")
        lines.append("# TYPE ledger_uptime_seconds gauge")

        # 输出所有 gauges
        with self._lock:
            for key, value in sorted(self._gauges.items()):
                lines.append(f"{key} {value}")

            # 输出所有 counters
            for key, value in sorted(self._counters.items()):
                lines.append(f"{key} {value}")

            # 输出直方图摘要
            for key, values in sorted(self._histograms.items()):
                if values:
                    lines.append(f"{key}_count {len(values)}")
                    lines.append(f"{key}_sum {sum(values)}")
                    sorted_vals = sorted(values)
                    lines.append(f'{key}{{quantile="0.5"}} {sorted_vals[len(sorted_vals)//2]}')
                    lines.append(f'{key}{{quantile="0.9"}} {sorted_vals[int(len(sorted_vals)*0.9)]}')
                    lines.append(f'{key}{{quantile="0.99"}} {sorted_vals[int(len(sorted_vals)*0.99)]}')

        return "\n".join(lines) + "\n"


class MetricsHandler(BaseHTTPRequestHandler):
    """Prometheus HTTP 处理器"""

    def do_GET(self):
        if self.path == "/metrics":
            collector = MetricsCollector()
            output = collector.get_prometheus_output()

            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(output.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # 静默 HTTP 请求日志
        pass


class MetricsServer:
    """Prometheus 指标服务器"""

    def __init__(self, port: int = None):
        self.port = port or ConfigManager.get_int("metrics.port", 9100)
        self._server = None
        self._thread = None

    def start(self):
        """启动指标服务器"""
        try:
            self._server = HTTPServer(("0.0.0.0", self.port), MetricsHandler)
            self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
            self._thread.start()
            log.info(f"Prometheus 指标服务已启动: http://0.0.0.0:{self.port}/metrics")
        except Exception as e:
            log.error(f"启动指标服务器失败: {e}")

    def stop(self):
        """停止指标服务器"""
        if self._server:
            self._server.shutdown()
            log.info("Prometheus 指标服务已停止")


# 便捷函数
_metrics_collector = None


def get_metrics_collector() -> MetricsCollector:
    """获取全局指标收集器"""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector


def counter_inc(name: str, value: float = 1.0, labels: Dict[str, str] = None):
    """增加计数器 (便捷函数)"""
    get_metrics_collector().counter_inc(name, value, labels)


def gauge_set(name: str, value: float, labels: Dict[str, str] = None):
    """设置仪表盘值 (便捷函数)"""
    get_metrics_collector().gauge_set(name, value, labels)


def histogram_observe(name: str, value: float, labels: Dict[str, str] = None):
    """记录直方图观测值 (便捷函数)"""
    get_metrics_collector().histogram_observe(name, value, labels)
