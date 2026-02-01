import os

# 定义项目根目录（当前文件在 src 下，所以取上一级）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_path(*args):
    """
    [Suggestion 1] 根据项目根目录构建绝对路径，支持环境感知
    """
    # 优先从环境变量读取数据根目录，支持沙箱隔离
    data_root = os.environ.get("LEDGER_DATA_ROOT", PROJECT_ROOT)
    
    # 特殊处理 docs 等只读资源，仍保留在项目根目录
    if args and args[0] in ("docs", "src", "config"):
        return os.path.join(PROJECT_ROOT, *args)
        
    return os.path.join(data_root, *args)
