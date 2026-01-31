import json
import re

def extract_json(text):
    """
    [Suggestion 1] 增强型 JSON 提取与修复算法
    支持处理：Markdown 包装、单引号、尾随逗号、截断文本
    """
    if not isinstance(text, str) or not text.strip():
        return None
        
    # 1. 预处理：移除 Markdown 代码块标记
    text = re.sub(r'```(?:json)?\s*(.*?)\s*```', r'\1', text, flags=re.DOTALL)
    
    # 2. 正则提取：递归寻找最外层大括号（贪婪匹配）
    try:
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if not match:
            return None
        
        json_str = match.group(0)
        
        # 3. 基础修复逻辑 (Heuristics)
        # a. 修复单引号为双引号
        # 注意：这里仅修复 key 和简单 value 的单引号，防止破坏内容中的引号
        json_str = re.sub(r"(['])\s*(\w+)\s*(['])\s*:", r'"\2":', json_str)
        # b. 移除尾随逗号 (如 {"a":1,})
        json_str = re.sub(r',\s*\}', '}', json_str)
        json_str = re.sub(r',\s*\]', ']', json_str)
        
        # 4. 尝试标准解析
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            # 5. 极端修复：处理被 LLM 截断的 JSON (尝试自动闭合)
            stack = []
            fixed_str = ""
            for char in json_str:
                fixed_str += char
                if char == '{': stack.append('}')
                elif char == '[': stack.append(']')
                elif char in ('}', ']'):
                    if stack and stack[-1] == char:
                        stack.pop()
            
            while stack:
                fixed_str += stack.pop()
            
            return json.loads(fixed_str)
    except Exception:
        return None
    return None
