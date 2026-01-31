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
        self.version = "v1.3.1"
        # 优化点：注册优雅退出清理回调
        register_cleanup(self.cleanup_processes)
        
        self.services = {
            "InteractionHub": get_path("src", "interaction_hub.py"),
            "Collector": get_path("src", "collector.py"),
            "MatchEngine": get_path("src", "match_engine.py")
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
        log.info("执行系统启动预检...")
        # 检查关键服务文件是否存在
        for name, path in self.services.items():
            if not os.path.exists(path):
                log.error(f"预检失败: 找不到服务文件 {name} -> {path}")
                return False
        
        # 检查数据库连接
        try:
            self.db.update_heartbeat("Master-Daemon", "STARTING")
        except Exception as e:
            log.error(f"预检失败: 数据库连接异常: {e}")
            return False
            
        log.info("预检通过。")
        return True

    def reload(self, signum, frame):
        log.info(f"接收到重载信号 (SIGHUP)，正在重启所有子服务以加载新配置... (Version: {self.version})")
        # 重置重试计数
        self.restart_counts = {}
        for name, proc in list(self.processes.items()):
            if proc:
                log.info(f"终止并准备重载: {name}")
                proc.terminate()

    def start_service(self, name, script_path):
        log.info(f"正在启动子服务: {name}")
        return subprocess.Popen([sys.executable, script_path])

    def shutdown(self, signum, frame):
        log.info("接收到退出信号，正在安全关闭所有子服务...")
        self.is_running = False
        
        # 1. 发送 SIGTERM 给所有子进程
        for name, proc in self.processes.items():
            if proc and proc.poll() is None:
                log.info(f"发送终止信号 (SIGTERM): {name}")
                proc.terminate()
        
        # 2. 等待子进程完成收尾（宽限期）
        grace_period = 5
        start_wait = time.time()
        while time.time() - start_wait < grace_period:
            active_procs = [n for n, p in self.processes.items() if p and p.poll() is None]
            if not active_procs:
                break
            log.info(f"正在等待子进程退出: {active_procs}...")
            time.sleep(1)
            
        # 3. 强制杀掉顽固进程
        for name, proc in self.processes.items():
            if proc and proc.poll() is None:
                log.warning(f"子进程 {name} 超时未退出，发送 SIGKILL 强制关机。")
                proc.kill()
                
        log.info("LedgerAlpha 系统已安全关闭。")
        sys.exit(0)

    def run(self):
        log.info(f"=== LedgerAlpha Master Daemon {self.version} 启动 ===")
        
        # [Suggestion 6] PID 文件加锁，防止多开
        pid_file = get_path("logs", "master.pid")
        if os.path.exists(pid_file):
            try:
                with open(pid_file, 'r') as f:
                    old_pid = int(f.read().strip())
                import psutil
                if psutil.pid_exists(old_pid):
                    # [Suggestion 5] 尝试优雅杀掉残留的子进程（如果父进程异常退出）
                    log.warning(f"检测到残留 PID {old_pid}，正在尝试清理可能存在的僵尸子进程...")
                    try:
                        parent = psutil.Process(old_pid)
                        for child in parent.children(recursive=True):
                            log.info(f"强制终止残留子进程: {child.pid}")
                            child.kill()
                        # parent.kill() # 不杀父进程，直接报错让用户检查
                    except:
                        pass
                    
                    log.error(f"系统已在运行 (PID: {old_pid})，请勿重复启动！")
                    return
            except:
                pass
        
        with open(pid_file, 'w') as f:
            f.write(str(os.getpid()))
            
        if not self._preflight_check():
            log.error("系统预检失败，程序退出。")
            return

        # 初始启动
        for name, path in self.services.items():
            self.processes[name] = self.start_service(name, path)
            self.restart_counts[name] = 0
            self.next_retry_time[name] = 0

        poll_interval = ConfigManager.get("intervals.daemon_poll", 5)
        backoff_base = ConfigManager.get("intervals.retry_backoff_base", 2)
        health_timeout = ConfigManager.get("intervals.health_timeout", 60)
        
        # 优化点：初始化工时统计
        last_metrics_update = 0

        while self.is_running and not should_exit():
            try:
                # 记录指标并更新心跳
                import psutil
                process = psutil.Process(os.getpid())
                
                # 业务指标统计 (Non-Functional 4.2)
                current_time = time.time()
                metrics = {
                    "cpu_percent": process.cpu_percent(),
                    "memory_mb": process.memory_info().rss / 1024 / 1024,
                    "threads": threading.active_count()
                }

                # 优化点：子进程资源熔断监控 (Suggestion 3)
                mem_limit_mb = ConfigManager.get("performance.proc_memory_limit_mb", 1024)
                for name, proc in self.processes.items():
                    try:
                        p = psutil.Process(proc.pid)
                        mem = p.memory_info().rss / 1024 / 1024
                        if mem > mem_limit_mb:
                            log.error(f"子进程 {name} 内存占用超限 ({mem:.1f}MB > {mem_limit_mb}MB)，触发保护性重启！")
                            proc.kill()
                    except:
                        pass

                # 优化点：Token 消耗熔断监控 (Non-Functional 4.2)
                token_budget = ConfigManager.get("performance.token_budget_daily", 5.0) # $5.0
                current_token_spend = self.db.get_daily_token_spend() # 假设库中已有统计
                if current_token_spend > token_budget:
                    log.critical(f"触发 Token 消耗熔断！今日支出 ${current_token_spend} 已超额度 ${token_budget}。")
                    # 执行紧急限流策略，如暂停非关键服务
                    self.is_running = False

                # 每 60 秒更新一次业务指标
                if current_time - last_metrics_update > 60:
                    try:
                        stats = self.db.get_ledger_stats()
                        processed_count = sum(s['count'] for s in stats if s['status'] in ('AUDITED', 'COMPLETED'))
                        metrics["human_hours_saved"] = (processed_count * 5) / 60.0
                        metrics["processed_count"] = processed_count
                        last_metrics_update = current_time
                    except:
                        pass

                self.db.update_heartbeat("Master-Daemon", "ACTIVE", metrics=json.dumps(metrics))
                
                # 检查子进程状态
                for name, proc in self.processes.items():
                    if should_exit(): break
                    
                    is_crashed = proc.poll() is not None
                    is_hung = False
                    
                    # 优化点：增加逻辑健康检查
                    if not is_crashed:
                        if not self.db.check_health(name, timeout_seconds=health_timeout):
                            log.warning(f"检测到子服务 {name} 心跳超时，判定为挂起 (Hung)！")
                            is_hung = True
                    
                    if is_crashed or is_hung:
                        if is_hung:
                            # 如果是挂起，先强制杀掉旧进程
                            log.info(f"强制终止挂起进程 -> {name}")
                            proc.kill()
                            proc.wait()

                        # 进程已退出或被杀
                        if current_time < self.next_retry_time.get(name, 0):
                            continue # 还在指数退避冷却期
                            
                        exit_code = proc.poll()
                        self.restart_counts[name] += 1
                        
                        # 优化点：异步指数退避，非阻塞主循环
                        wait_time = min(60, backoff_base ** (self.restart_counts[name] - 1))
                        log.warning(f"服务 {name} 异常重启 (退出码: {exit_code})，第 {self.restart_counts[name]} 次。冷却 {wait_time}s...")
                        
                        self.next_retry_time[name] = current_time + wait_time
                        self.processes[name] = self.start_service(name, self.services[name])
                    else:
                        # 运行正常，重置计数
                        self.restart_counts[name] = 0
                        self.next_retry_time[name] = 0
                
                time.sleep(poll_interval)
            except InterruptedError:
                break
            except Exception as e:
                log.error(f"Daemon 主循环异常: {e}")
                time.sleep(poll_interval)

if __name__ == "__main__":
    daemon = MasterDaemon()
    daemon.run()
