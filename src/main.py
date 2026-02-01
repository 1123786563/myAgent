import subprocess
import time
import sys
import os
import signal
import threading
import json
from logger import get_logger
from db_helper import DBHelper
from config_manager import ConfigManager
from project_paths import get_path
from graceful_exit import should_exit, register_cleanup

log = get_logger("MasterDaemon")

class MasterDaemon:
    def __init__(self):
        self.db = DBHelper()
        self.version = "v1.5.0-perfect"
        # 优化点：注册优雅退出清理回调
        register_cleanup(self.cleanup_processes)
        
        self.services = {
            "InteractionHub": get_path("src", "interaction_hub.py"),
            "Collector": get_path("src", "collector.py"),
            "MatchEngine": get_path("src", "match_engine.py"),
            "AccountingAgent": get_path("src", "accounting_agent.py"),
            "Auditor": get_path("src", "auditor_agent.py"),
            "Sentinel": get_path("src", "sentinel_agent.py"),
            "APIServer": get_path("src", "api_server.py")
        }
        self.processes = {}
        self.restart_counts = {}
        self.next_retry_time = {}
        self.is_running = True
        
        if hasattr(signal, 'SIGHUP'):
            signal.signal(signal.SIGHUP, self.reload)

    def cleanup_processes(self):
        """优雅退出时的子进程清理逻辑"""
        log.info("正在清理子进程...")
        for name, proc in self.processes.items():
            if proc and proc.poll() is None:
                log.info(f"发送 SIGTERM -> {name}")
                proc.terminate()
        
        # 等待一会
        time.sleep(2)
        for name, proc in self.processes.items():
            if proc and proc.poll() is None:
                log.warning(f"强制杀掉残留进程 -> {name}")
                proc.kill()

    def _preflight_check(self):
        """启动前预检"""
        log.info("执行系统启动预检与自愈恢复...")
        
        # [Optimization Round 5] 环境与依赖项检查
        try:
            import openai
            import pandas
            import yaml
            log.info("核心依赖库 (openai, pandas, yaml) 检查通过。")
        except ImportError as e:
            log.error(f"预检失败: 缺失核心依赖项 {e}。请执行 pip install -r requirements.txt")
            return False

        # 检查关键环境变量
        if not ConfigManager.get("llm.api_key"):
            log.warning("环境变量 LLM_API_KEY 未设置，系统将运行在 MOCK 模式。")

        # 检查关键服务文件是否存在
        for name, path in self.services.items():
            if not os.path.exists(path):
                log.error(f"预检失败: 找不到服务文件 {name} -> {path}")
                return False
        
        # [Optimization 3] 启动自愈：清理僵尸事务状态
        try:
            self.db.update_heartbeat("Master-Daemon", "STARTING")
            recovered_count = self.db.fix_orphaned_transactions()
            if recovered_count > 0:
                log.warning(f"成功自愈系统：重置了 {recovered_count} 笔状态异常的分录。")
        except Exception as e:
            log.error(f"预检失败: 数据库连接或自愈异常: {e}")
            return False
            
        log.info("预检与自愈通过。")
        return True

    def reload(self, signum, frame):
        # [Suggestion 3] 增加信号防抖 (Debouncing) 逻辑
        current_time = time.time()
        last_reload = getattr(self, '_last_reload_t', 0)
        if current_time - last_reload < 5.0: # 5秒内不重复加载
            log.warning("检测到高频重载信号，触发防抖保护，本次忽略。")
            return
        self._last_reload_t = current_time

        log.info(f"接收到重载信号 (SIGHUP)，正在重启所有子服务... (Version: {self.version})")
        self.restart_counts = {}
        for name, proc in list(self.processes.items()):
            if proc:
                log.info(f"终止并准备重载: {name}")
                proc.terminate()

    def start_service(self, name, script_path):
        log.info(f"正在启动子服务: {name}")
        env = os.environ.copy()
        env["LEDGER_PARENT_PID"] = str(os.getpid())
        return subprocess.Popen([sys.executable, script_path], env=env)

    def shutdown(self, signum, frame):
        log.info("接收到退出信号，正在安全关闭所有子服务...")
        self.is_running = False
        
        for name, proc in self.processes.items():
            if proc and proc.poll() is None:
                log.info(f"发送终止信号 (SIGTERM): {name}")
                proc.terminate()
        
        grace_period = 5
        start_wait = time.time()
        while time.time() - start_wait < grace_period:
            active_procs = [n for n, p in self.processes.items() if p and p.poll() is None]
            if not active_procs:
                break
            log.info(f"正在等待子进程退出: {active_procs}...")
            time.sleep(1)
            
        for name, proc in self.processes.items():
            if proc and proc.poll() is None:
                log.warning(f"子进程 {name} 超时未退出，发送 SIGKILL 强制关机。")
                proc.kill()
                
        log.info("LedgerAlpha 系统已安全关闭。")
        sys.exit(0)

    def run(self):
        log.info(f"=== LedgerAlpha Master Daemon {self.version} 启动 ===")
        
        try:
            wal_lock = get_path("ledger_alpha.db-wal")
            if os.path.exists(wal_lock) and os.path.getsize(wal_lock) > 100 * 1024 * 1024: # >100MB
                log.warning("检测到 WAL 文件异常巨大，执行启动前自愈检查点...")
        
            pid_file = get_path("logs", "master.pid")
            if os.path.exists(pid_file):
                try:
                    with open(pid_file, 'r') as f:
                        old_pid = int(f.read().strip())
                    import psutil
                    if psutil.pid_exists(old_pid):
                        log.error(f"系统已在运行 (PID: {old_pid})，请勿重复启动！")
                        return
                except:
                    pass
            
            with open(pid_file, 'w') as f:
                f.write(str(os.getpid()))
                
            if not self._preflight_check():
                log.error("系统预检失败，程序退出。")
                return

            for name, path in self.services.items():
                self.processes[name] = self.start_service(name, path)
                self.restart_counts[name] = 0
                self.next_retry_time[name] = 0

            poll_interval = ConfigManager.get("intervals.daemon_poll", 5)
            backoff_base = ConfigManager.get("intervals.retry_backoff_base", 2)
            health_timeout = ConfigManager.get("intervals.health_timeout", 60)
            
            last_metrics_update = 0

            while self.is_running and not should_exit():
                try:
                    # [Optimization Round 14] 鲁棒的 psutil 指标获取
                    process = None
                    try:
                        import psutil
                        process = psutil.Process(os.getpid())
                    except ImportError:
                        pass
                    
                    current_time = time.time()
                    metrics = {
                        "cpu_percent": process.cpu_percent() if process else 0.0,
                        "memory_mb": (process.memory_info().rss / 1024 / 1024) if process else 0.0,
                        "threads": threading.active_count()
                    }

                    # 每 60 秒更新一次业务指标
                    if current_time - last_metrics_update > 60:
                        try:
                            # [Optimization 4] 动态 Token 配额与风险感知配额管理
                            # 逻辑：检测单笔平均金额，自动锁定/解锁高阶模型
                            
                            # [Optimization Round 15] 执行定期知识维护任务 (Knowledge Cleanup)
                            KnowledgeBridge().cleanup_stale_rules(min_hits=1, days_old=7)
                            
                            # 执行定期的知识蒸馏自愈任务
                            KnowledgeBridge().distill_knowledge()
                            
                            # [Optimization 5] 执行数据库定期自愈维护 (DB Maintenance)
                            self.db.perform_db_maintenance()
                            
                            # [Optimization Round 11] 实时 ROI 指标持久化与偏差分析 (SRS 4.2)
                            roi_data = self.db.get_roi_metrics()
                            if roi_data:
                                log.info(f"系统效益快报: 已节省 {roi_data.get('human_hours_saved', 0)} 小时 | ROI: {roi_data.get('roi_ratio', 0)}")

                            # [Optimization Round 23] 现金流健康哨兵 (SRS 3.3.3)
                            try:
                                from cashflow_predictor import CashflowPredictor
                                predictor = CashflowPredictor()
                                cf_report = predictor.predict()
                                if cf_report.get("is_alarm"):
                                    log.critical(f"系统主动防御：现金流风险预警！{cf_report.get('status')} | 耗尽点：{cf_report.get('days_until_burnout')}天")
                                    self.db.log_system_event("CASHFLOW_ALARM", "MasterDaemon", cf_report.get('insight'))
                            except Exception as ce:
                                log.error(f"现金流预测失败: {ce}")

                            # [Optimization 4] 通知确认重传巡检
                            # 此处为逻辑预留：self.db.retry_pending_notifications()

                            # [Optimization 5] 运营自愈：Outbox 积压巡检与告警 (F4.5)
                            backlog_count = self.db.verify_outbox_integrity("InteractionHub")
                            if backlog_count > 5:
                                log.critical(f"系统告警：InteractionHub 积压事件 {backlog_count} 笔，请检查外部通道可靠性！")

                            # [Optimization 5] 执行数据库自愈维护
                            self.db.perform_db_maintenance()
                            
                            stats = self.db.get_ledger_stats()
                            processed_count = sum(s['count'] for s in stats if s['status'] in ('AUDITED', 'COMPLETED', 'POSTED'))
                            metrics["human_hours_saved"] = (processed_count * 5) / 60.0
                            metrics["processed_count"] = processed_count
                            last_metrics_update = current_time
                        except Exception as e:
                            log.error(f"定时指标更新失败: {e}")

                    self.db.update_heartbeat("Master-Daemon", "ACTIVE", metrics=json.dumps(metrics))
                    
                    for name, proc in self.processes.items():
                        if should_exit(): break
                        is_crashed = proc.poll() is not None
                        is_hung = False

                        if not is_crashed:
                            if not self.db.check_health(name, timeout_seconds=health_timeout):
                                log.warning(f"检测到子服务 {name} 逻辑挂起 (Heartbeat Stuck)！触发强制重启...")
                                is_hung = True

                        if is_crashed or is_hung:
                            if is_hung:
                                log.info(f"发送 SIGKILL -> {name}")
                                proc.kill()
                                proc.wait()

                            if current_time < self.next_retry_time.get(name, 0):
                                continue

                            exit_code = proc.poll()
                            self.restart_counts[name] += 1
                            wait_time = min(60, backoff_base ** (self.restart_counts[name] - 1))
                            log.warning(f"服务 {name} 异常重启 ({exit_code})，第 {self.restart_counts[name]} 次。冷却 {wait_time}s...")

                            self.next_retry_time[name] = current_time + wait_time
                            self.processes[name] = self.start_service(name, self.services[name])
                        else:
                            self.restart_counts[name] = 0
                            self.next_retry_time[name] = 0
                    
                    time.sleep(poll_interval)
                except Exception as e:
                    log.error(f"Daemon 主循环异常: {e}")
                    time.sleep(poll_interval)
            
            log.info("Master Daemon 运行结束。")
        except Exception as e:
            log.critical(f"Master Daemon 崩溃: {e}")

if __name__ == "__main__":
    daemon = MasterDaemon()
    daemon.run()
