import sys
import os

# Add src to PYTHONPATH
# SRC_DIR should be /Users/yongjunwu/trea/myAgent/src
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
# PROJECT_ROOT should be /Users/yongjunwu/trea/myAgent
PROJECT_ROOT = os.path.dirname(SRC_DIR)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

# Add subdirectories to PYTHONPATH
for sub in ["core", "infra", "utils", "agents", "engine", "api"]:
    sub_path = os.path.join(SRC_DIR, sub)
    if sub_path not in sys.path:
        sys.path.insert(0, sub_path)
