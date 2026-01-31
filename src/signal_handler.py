import signal

# 全局状态标志
_shutting_down = False

def handle_signal(signum, frame):
    global _shutting_down
    print(f"\n[Signal] 捕获信号 {signum}，准备优雅退出...")
    _shutting_down = True

def install_handlers():
    """安装退出信号处理器"""
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

def is_active():
    """检查当前服务是否应当继续运行"""
    return not _shutting_down
