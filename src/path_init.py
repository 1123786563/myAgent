import sys
import os

# Add src to PYTHONPATH
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

# Add subdirectories to PYTHONPATH
for sub in ["core", "infra", "utils", "agents", "engine", "api"]:
    sub_path = os.path.join(SRC_DIR, sub)
    if sub_path not in sys.path:
        sys.path.insert(0, sub_path)
