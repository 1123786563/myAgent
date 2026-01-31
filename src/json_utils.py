import json
import re

def extract_json(text):
    """
    从杂乱的文字中精准提取 JSON 块并尝试修复
    支持 ```json ... ``` 包裹或直接出现的第一个 { ... }
    """
    if not isinstance(text, str):
        return None
        
    # 1. 尝试直接解析
    try:
        return json.loads(text)
    except Exception:
        pass
        
    # 2. 正则提取最外层大括号
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        clean_text = match.group(0)
        try:
            return json.loads(clean_text)
        except Exception:
            # 3. 简单的自动闭合和修复（如删除末尾逗号）
            clean_text = re.sub(r',\s*\}', '}', clean_text)
            try:
                return json.loads(clean_text)
            except Exception:
                return None
    return None
