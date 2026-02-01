import signal
import sys
import time
import threading
from logger import get_logger

log = get_logger("GracefulExit")

class GracefulExit:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(GracefulExit, cls).__new__(cls)
                cls._instance.stop_event = threading.Event()
                cls._instance.callbacks = []
                cls._instance.is_shutting_down = False
                cls._instance._install_handlers()
        return cls._instance

    def _install_handlers(self):
        signal.signal(signal.SIGINT, self._handler)
        signal.signal(signal.SIGTERM, self._handler)
        # [Suggestion 2] 启动父进程探测器 (Watchdog)
        threading.Thread(target=self._parent_watchdog, daemon=True).start()

    def _parent_watchdog(self):
        """如果父进程挂掉，子进程自动殉情自杀，防止僵尸进程"""
        import os
        parent_pid = int(os.environ.get("LEDGER_PARENT_PID", 0))
        if parent_pid == 0:
            return
            
        import psutil
        while not self.stop_event.is_set():
            try:
                # 检查父进程是否仍然存活
                if not psutil.pid_exists(parent_pid):
                    log.error(f"父进程 {parent_pid} 已消失！子进程触发‘殉情’逻辑自动退出...")
                    self._handler(signal.SIGTERM, None)
                    break
            except Exception:
                pass
            time.sleep(5) # 每 5 秒巡检一次

    def _handler(self, sig, frame):
        if self.is_shutting_down:
            log.warning("检测到重复退出信号，请耐心等待清理完成...")
            return
            
        log.info(f"接收到系统信号 {sig}，准备执行优雅退出...")
        self.is_shutting_down = True
        self.stop_event.set()
        
        # 启动退出兜底定时器：10秒后强制退出
        threading.Thread(target=self._hard_exit_watchdog, daemon=True).start()
        
        # 执行注册的回调
        self._run_cleanup()
        
        log.info("所有清理工作已完成，系统退出。")
        sys.exit(0)

    def _hard_exit_watchdog(self):
        time.sleep(10)
        log.error("优雅退出超时（10s），触发强行关闭！")
        os._exit(1)

    def register_cleanup(self, func, *args, **kwargs):
        """注册清理回调函数"""
        self.callbacks.append((func, args, kwargs))

    def _run_cleanup(self):
        for func, args, kwargs in self.callbacks:
            try:
                log.info(f"正在执行清理任务: {func.__name__}")
                func(*args, **kwargs)
            except Exception as e:
                log.error(f"清理任务执行失败: {func.__name__} | {e}")

    def should_exit(self):
        return self.stop_event.is_set()

# 单例便捷访问
exit_handler = GracefulExit()

def register_cleanup(func, *args, **kwargs):
    exit_handler.register_cleanup(func, *args, **kwargs)

def should_exit():
    return exit_handler.should_exit()

def get_stop_event():
    return exit_handler.stop_event
