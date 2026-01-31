import yaml
import shutil
import os

def safe_update_yaml(path, new_rules):
    """
    预校验 + 备份更新 YAML
    """
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                yaml.safe_load(f) # 试读
        except Exception:
            print(f"警告：配置文件 {path} 结构已损坏，尝试使用备份恢复。")
            # 恢复逻辑...
            return False
            
    # 执行备份并写入新规则...
    return True
