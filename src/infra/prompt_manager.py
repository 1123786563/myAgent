"""
[Optimization Iteration 4] Prompt 版本管理器
[Optimization Iteration 6] 增加动态参数替换支持

支持从 YAML 文件加载多版本 Prompt，便于 A/B 测试和回滚。
"""

import os
import re
import time
import threading
from typing import Dict, Optional, Any, List
from logger import get_logger
from project_paths import get_path
from config_manager import ConfigManager

log = get_logger("PromptManager")


class PromptVersion:
    """Prompt 版本数据类"""
    def __init__(self, name: str, content: str, version: str = "1.0",
                 description: str = "", metadata: Dict = None):
        self.name = name
        self.content = content
        self.version = version
        self.description = description
        self.metadata = metadata or {}
        self.created_at = time.time()
        self.use_count = 0

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "content_length": len(self.content),
            "use_count": self.use_count
        }


class PromptManager:
    """
    Prompt 版本管理器

    使用示例:
        manager = PromptManager()
        prompt = manager.get_prompt("accounting_classifier")
        prompt_v2 = manager.get_prompt("accounting_classifier", version="2.0")
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init()
        return cls._instance

    def _init(self):
        self.prompts: Dict[str, Dict[str, PromptVersion]] = {}
        self.default_versions: Dict[str, str] = {}
        self.prompts_path = get_path("config", "prompts.yaml")
        self._last_loaded = 0
        self._stats = {
            "total_calls": 0,
            "cache_hits": 0,
            "versions_loaded": 0
        }
        self._load_prompts()

    def _load_prompts(self):
        """从 YAML 文件加载 Prompt 配置"""
        try:
            import yaml
            if not os.path.exists(self.prompts_path):
                self._load_default_prompts()
                return

            # 检查文件是否更新
            mtime = os.path.getmtime(self.prompts_path)
            if mtime <= self._last_loaded and self.prompts:
                return

            with open(self.prompts_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}

            prompts_data = data.get("prompts", [])
            for p in prompts_data:
                name = p.get("name")
                if not name:
                    continue

                version = p.get("version", "1.0")
                prompt_obj = PromptVersion(
                    name=name,
                    content=p.get("content", ""),
                    version=version,
                    description=p.get("description", ""),
                    metadata=p.get("metadata", {})
                )

                if name not in self.prompts:
                    self.prompts[name] = {}
                self.prompts[name][version] = prompt_obj

                # 设置默认版本
                if p.get("default", False) or name not in self.default_versions:
                    self.default_versions[name] = version

            self._last_loaded = mtime
            self._stats["versions_loaded"] = sum(len(v) for v in self.prompts.values())
            log.info(f"已加载 {len(self.prompts)} 个 Prompt，共 {self._stats['versions_loaded']} 个版本")

        except Exception as e:
            log.error(f"加载 Prompt 配置失败: {e}")
            self._load_default_prompts()

    def _load_default_prompts(self):
        """加载默认内置 Prompt"""
        default_accounting = PromptVersion(
            name="accounting_classifier",
            version="1.0",
            description="会计分类助手默认 Prompt",
            content="""你是一个专业的会计分类助手，负责将交易信息分类到正确的会计科目。

你的任务是：
1. 分析交易描述和供应商信息
2. 确定最合适的会计科目分类
3. 给出分类理由
4. 评估分类置信度 (0-1)

请以 JSON 格式返回结果：
{
    "category": "会计科目名称",
    "reason": "分类理由",
    "confidence": 0.95
}

常见科目包括：技术服务费、业务招待费、差旅费-交通费、办公设备、办公用品、水电费、房租、薪酬福利、广告宣传费、杂项支出等。"""
        )

        self.prompts["accounting_classifier"] = {"1.0": default_accounting}
        self.default_versions["accounting_classifier"] = "1.0"
        log.info("已加载默认 Prompt 配置")

    def get_prompt(self, name: str, version: str = None) -> Optional[str]:
        """
        获取 Prompt 内容

        Args:
            name: Prompt 名称
            version: 版本号，不指定则使用默认版本

        Returns:
            Prompt 内容字符串
        """
        self._stats["total_calls"] += 1

        # 检查是否需要重新加载
        if time.time() - self._last_loaded > 60:
            self._load_prompts()

        if name not in self.prompts:
            log.warning(f"未找到 Prompt: {name}")
            return None

        if version is None:
            version = self.default_versions.get(name, "1.0")

        versions = self.prompts[name]
        if version not in versions:
            log.warning(f"未找到 Prompt 版本: {name}@{version}")
            # 回退到默认版本
            version = self.default_versions.get(name)
            if version not in versions:
                return None

        prompt_obj = versions[version]
        prompt_obj.use_count += 1
        self._stats["cache_hits"] += 1

        log.debug(f"使用 Prompt: {name}@{version} (第 {prompt_obj.use_count} 次调用)")
        return prompt_obj.content

    def get_prompt_object(self, name: str, version: str = None) -> Optional[PromptVersion]:
        """获取 Prompt 对象"""
        if name not in self.prompts:
            return None

        if version is None:
            version = self.default_versions.get(name, "1.0")

        return self.prompts.get(name, {}).get(version)

    def set_default_version(self, name: str, version: str) -> bool:
        """设置默认版本"""
        if name not in self.prompts or version not in self.prompts[name]:
            return False
        self.default_versions[name] = version
        log.info(f"已设置 {name} 默认版本为 {version}")
        return True

    def list_prompts(self) -> Dict[str, list]:
        """列出所有 Prompt 及其版本"""
        result = {}
        for name, versions in self.prompts.items():
            result[name] = [
                {
                    "version": v.version,
                    "description": v.description,
                    "use_count": v.use_count,
                    "is_default": self.default_versions.get(name) == v.version
                }
                for v in versions.values()
            ]
        return result

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self._stats.copy()

    def reload(self):
        """强制重新加载"""
        self._last_loaded = 0
        self._load_prompts()

    def render_prompt(self, name: str, params: Dict[str, Any] = None,
                      version: str = None) -> Optional[str]:
        """
        [Optimization Iteration 6] 获取并渲染 Prompt，支持动态参数替换

        Args:
            name: Prompt 名称
            params: 参数字典，如 {"vendor": "阿里云", "amount": 1000}
            version: 版本号

        Returns:
            渲染后的 Prompt 内容

        示例:
            prompt = manager.render_prompt("accounting_classifier", {
                "vendor": "阿里云",
                "amount": 1000,
                "date": "2026-01-31"
            })
        """
        content = self.get_prompt(name, version)
        if content is None:
            return None

        if params:
            content = self._substitute_params(content, params)

        return content

    def _substitute_params(self, content: str, params: Dict[str, Any]) -> str:
        """
        替换 Prompt 中的占位符

        支持的格式:
        - {param_name} - 简单替换
        - {param_name:default} - 带默认值的替换
        - {{param_name}} - 转义，保留原样
        """
        # 处理转义的双花括号
        content = content.replace("{{", "\x00ESCAPED_OPEN\x00")
        content = content.replace("}}", "\x00ESCAPED_CLOSE\x00")

        # 替换带默认值的占位符: {name:default}
        def replace_with_default(match):
            key = match.group(1)
            default = match.group(2)
            return str(params.get(key, default))

        content = re.sub(r'\{(\w+):([^}]*)\}', replace_with_default, content)

        # 替换简单占位符: {name}
        def replace_simple(match):
            key = match.group(1)
            if key in params:
                return str(params[key])
            log.warning(f"Prompt 参数未提供: {key}")
            return match.group(0)  # 保留原样

        content = re.sub(r'\{(\w+)\}', replace_simple, content)

        # 恢复转义的花括号
        content = content.replace("\x00ESCAPED_OPEN\x00", "{")
        content = content.replace("\x00ESCAPED_CLOSE\x00", "}")

        return content

    def get_prompt_params(self, name: str, version: str = None) -> List[str]:
        """
        [Optimization Iteration 6] 提取 Prompt 中的参数占位符

        Returns:
            参数名列表
        """
        content = self.get_prompt(name, version)
        if content is None:
            return []

        # 查找所有 {param} 格式的占位符
        # 排除转义的 {{param}}
        params = re.findall(r'(?<!\{)\{(\w+)(?::[^}]*)?\}(?!\})', content)
        return list(set(params))
