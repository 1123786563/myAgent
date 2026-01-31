import re
from functools import lru_cache
from config_manager import ConfigManager

class PrivacyGuard:
    def __init__(self, role="GUEST"):
        # 优化点：基于角色的脱敏等级控制
        self.role = role
        self.phone_pattern = re.compile(r'(1[3-9]\d)(\d{4})(\d{4})')
        self.id_card_pattern = re.compile(r'(\d{4})\d{10,13}(\d{2}[0-9xX])')
        self.bank_card_pattern = re.compile(r'(\d{4})\d{8,11}(\d{4})')
        
        self.mask_char = ConfigManager.get("privacy.mask_char", "*")
        self.custom_keywords = ConfigManager.get("privacy.keywords") or []
        self._update_keyword_pattern()

    def _update_keyword_pattern(self):
        # 优化点：动态合并配置与数据库敏感词
        db_keywords = self._get_db_keywords()
        all_keywords = list(set(self.custom_keywords + db_keywords))
        
        if all_keywords:
            escaped = [re.escape(k) for k in all_keywords]
            self.keyword_pattern = re.compile(f"({'|'.join(escaped)})")
        else:
            self.keyword_pattern = None

    def _get_db_keywords(self):
        """模拟从数据库加载动态敏感词库"""
        # 实际应调用 DBHelper 查询某张敏感词表
        return ["薪资", "机密项目", "偷税", "漏税", "个税申报", "法人借款"]

    @lru_cache(maxsize=128)
    def desensitize(self, text, bypass_role="ADMIN", context="GENERAL", data_type="DEFAULT"):
        if not isinstance(text, str) or not text:
            return text
        
        # 1. 权限绕过检查
        if self.role == bypass_role:
            return text
            
        new_text = text
        
        # [Optimization 3] 基于上下文的敏感度升级 (Context-Aware Masking)
        # 定义不同上下文的敏感关键词映射
        context_risks = {
            "PAYROLL": ["工资", "薪金", "奖金", "社保", "公积金"],
            "LEGAL": ["诉讼", "纠纷", "赔偿", "判决"],
            "STRATEGIC": ["收购", "合并", "融资", "估值"]
        }
        
        # 检查当前上下文是否触发高级屏蔽
        sensitive_keywords = context_risks.get(context, [])
        
        # 隐式语义上下文推断 (如果 context 是 GENERAL)
        if context == "GENERAL":
            for ctx, kws in context_risks.items():
                if any(kw in text for kw in kws):
                    sensitive_keywords.extend(kws)
                    context = ctx # 升级上下文
        
        # 如果命中了敏感上下文，执行整句掩码或高强度掩码
        if sensitive_keywords:
            if context == "STRATEGIC" and self.role != "BOSS":
                 return f"[TOP_SECRET_{context}_MASKED]"
            
            # 对于其他敏感上下文，对数值进行全部掩盖
            new_text = re.sub(r'\d{3,}', '***', new_text)

        # [Optimization 3] 战略合同敏感脱敏 (Strategic Masking)
        # 如果是战略级合同或敏感财务关键词，即使是 AUDITOR 也强制深度脱敏
        if context in ("STRATEGIC_CONTRACT", "STRATEGIC") or any(kw in text for kw in ["战略合作", "融资意向"]):
             return f"[SENSITIVE_CONTEXT_MASKED_{self.mask_char*4}]"

        # 优化点：基于上下文和财务合规敏感度的分级脱敏 (F4.1)
        # 如果是敏感财务关键词，无论角色均执行高级掩码
        if any(kw in text for kw in ["薪资", "法人借款", "机密项目"]):
            return f"[FINANCIAL_PROTECTED_{self.mask_char*4}]"

        # 2. 正则脱敏
        is_sensitive_context = context in ("NOTE", "COMMENT", "GENERAL")
        
        if is_sensitive_context:
            if self.role == "AUDITOR":
                new_text = self.phone_pattern.sub(rf"\1{self.mask_char*4}\3", new_text)
                new_text = self.id_card_pattern.sub(rf"\1{self.mask_char*10}\2", new_text)
                new_text = self.bank_card_pattern.sub(rf"\1{self.mask_char*8}\2", new_text)
            else:
                new_text = self.phone_pattern.sub("[PHONE_SECRET]", new_text)
                new_text = self.id_card_pattern.sub("[ID_SECRET]", new_text)
                new_text = self.bank_card_pattern.sub("[BANK_SECRET]", new_text)
        
        # 3. 关键词脱敏
        if self.keyword_pattern:
            if self.role == "AUDITOR":
                new_text = self.keyword_pattern.sub(lambda m: self.mask_char * len(m.group(0)), new_text)
            else:
                new_text = self.keyword_pattern.sub("[SECRET]", new_text)
        
        if new_text != text:
            # 优化点：记录脱敏事件（但不记录内容）
            # log.debug(f"PrivacyGuard: 文本在上下文 [{context}] 中触发脱敏规则")
            pass
            
        return new_text

    def semantic_desensitize(self, text):
        """
        [Optimization 3] 边缘计算隐私网关：语义脱敏增强 (白皮书 2.3)
        """
        # 简化逻辑：如果识别到复杂敏感语义，直接截断并返回摘要
        if len(text) > 100 and "合同" in text:
             return f"[SEMANTIC_SUMMARY]: 涉及合同条款的敏感业务逻辑"
        return self.desensitize(text)

if __name__ == "__main__":
    guard = PrivacyGuard()
    raw = "手机13812345678"
    print(guard.desensitize(raw))
    print(guard.desensitize(raw)) # 命中缓存
