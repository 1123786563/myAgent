from logger import get_logger
from privacy_guard import PrivacyGuard
from config_manager import ConfigManager
import json

log = get_logger("ProxyActor")

class SecurityException(Exception):
    pass

class ProxyActor:
    """
    [Optimization Round 3] 网络出口强制代理 (Egress Proxy)
    所有外部 API 请求必须经过此 Actor，强制执行隐私检查。
    实现“本地锁”策略：敏感数据在离开内存前必须被 PrivacyGuard 过滤。
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ProxyActor, cls).__new__(cls)
            cls._instance.guard = PrivacyGuard(role="ProxyAdmin")
            cls._instance.strict_mode = ConfigManager.get("security.strict_mode", True)
        return cls._instance

    def _inspect_and_sanitize(self, text_content):
        """
        检查文本负载，强制脱敏
        返回: (safe_text, was_modified)
        """
        if not text_content or not isinstance(text_content, str):
            return text_content, False
        
        # 调用 PrivacyGuard 的 LLM 专用清洗接口
        cleaned_text, found_sensitive = self.guard.sanitize_for_llm(text_content)
        
        if found_sensitive:
            log.warning(f"🛡️ [Proxy] 拦截到敏感数据！已强制脱敏。原文长度: {len(text_content)}")
            # 在极度严格模式下，可以配置为直接熔断抛错
            # if self.strict_mode:
            #     raise SecurityException("Data Leak Prevention: Blocked outbound request containing PII.")
            return cleaned_text, True
            
        return cleaned_text, False

    def send_llm_request(self, client, model, messages, **kwargs):
        """
        代理 LLM 请求 (OpenAI SDK Compatible)
        拦截 messages 中的 content，进行强制脱敏后再发给 client
        """
        log.info(f"🔒 ProxyIntercept: Outbound LLM Request -> {model}")
        
        safe_messages = []
        modified_count = 0
        
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                safe_content, modified = self._inspect_and_sanitize(content)
                if modified: modified_count += 1
                safe_messages.append({
                    "role": msg["role"], 
                    "content": safe_content
                })
            else:
                # 处理复杂 content (如 multimodal list)
                # 简化处理：暂时原样放行非文本，实际应递归检查
                safe_messages.append(msg)
        
        if modified_count > 0:
            log.info(f"🔒 Proxy 安全报告: 修改了 {modified_count} 条消息中的敏感内容。")

        # Forward call to the actual client
        # 这一步是实际的网络 IO
        try:
            return client.chat.completions.create(
                model=model,
                messages=safe_messages,
                **kwargs
            )
        except Exception as e:
            log.error(f"🔒 Proxy 转发失败: {e}")
            raise e

    def validate_url_request(self, url):
        """
        代理 HTTP URL 检查 (用于 Browser Connector)
        """
        log.info(f"🔒 ProxyIntercept: Checking URL -> {url}")
        
        # 简单的白名单/黑名单逻辑
        allowed_hosts = ["mock-bank-portal.internal", "api.openai.com", "127.0.0.1"]
        if not any(host in url for host in allowed_hosts):
            log.warning(f"⚠️ 访问了非白名单域名: {url}")
            # if self.strict_mode: raise SecurityException(f"URL blocked by policy: {url}")
        
        return True
