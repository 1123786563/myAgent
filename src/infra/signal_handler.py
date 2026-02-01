import signal

# 全局状态标志
_shutting_down = False

def handle_signal(signum, frame):
    global _shutting_down
    if signum in (signal.SIGINT, signal.SIGTERM):
        print(f"\n[Signal] 捕获信号 {signum}，准备优雅退出...")
        _shutting_down = True
    elif signum == signal.SIGUSR1:
        # [Suggestion 2] 触发任务快照导出
        print(f"\n[Signal] 捕获 SIGUSR1，正在触发任务快照导出...")
    elif signum == signal.SIGUSR2:
        # [Suggestion 1] 动态调整日志级别并重载配置
        from logger import get_logger
        from config_manager import ConfigManager
        ConfigManager.load(force=True)
        log = get_logger("System")
        log.info("捕获 SIGUSR2，配置已重载并动态切换日志级别至 DEBUG")

def install_handlers():
    """安装退出信号处理器"""
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    # 增加高级信号支持
    if hasattr(signal, 'SIGUSR1'):
        signal.signal(signal.SIGUSR1, handle_signal)
    if hasattr(signal, 'SIGUSR2'):
        signal.signal(signal.SIGUSR2, handle_signal)

def is_active():
    """检查当前服务是否应当继续运行"""
    return not _shutting_down
