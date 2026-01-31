import yaml
import shutil
import os
import tempfile

def safe_update_yaml(path, data):
    """
    [Suggestion 1] 原子化、安全地更新 YAML 文件
    原理：写入临时文件 -> 校验 -> 重命名覆盖
    """
    dir_name = os.path.dirname(path)
    # 1. 生成临时文件
    fd, temp_path = tempfile.mkstemp(dir=dir_name, text=True)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            yaml.safe_dump(data, f, allow_unicode=True, default_flow_style=False)
        
        # 2. 写后即读校验 (Suggestion 2)
        with open(temp_path, 'r', encoding='utf-8') as f:
            check_data = yaml.safe_load(f)
            if not check_data:
                raise ValueError("YAML 写入校验失败：文件内容为空")
        
        # 3. 备份旧文件并重命名覆盖（原子操作）
        if os.path.exists(path):
            shutil.copy2(path, path + ".bak")
        os.replace(temp_path, path)
        return True
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        print(f"YAML 安全更新失败: {e}")
        return False
