import os

# 定义项目根目录（当前文件在 src 下，所以取上一级）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_path(*args):
    """根据项目根目录构建绝对路径"""
    return os.path.join(PROJECT_ROOT, *args)
