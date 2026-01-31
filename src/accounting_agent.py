import yaml
import re
import os
import hashlib
import operator
from pathlib import Path
from bus_init import LedgerMsg
from agentscope.agents import AgentBase
from logger import get_logger
from project_paths import get_path

log = get_logger("AccountingAgent")

class AccountingAgent(AgentBase):
    def __init__(self, name, rules_path=None):
        super().__init__(name=name)
        # 优化点：集成 project_paths 和 Pathlib
        self.rules_path = Path(rules_path or get_path("src", "accounting_rules.yaml"))
        self.rules = []
        self._rules_hash = None
        self._load_rules()
        
        # 逻辑运算符映射
        self.ops = {
            ">": operator.gt,
            "<": operator.lt,
            "==": operator.eq,
            ">=": operator.ge,
            "<=": operator.le,
            "in": lambda x, y: x in y if isinstance(y, (list, str)) else False
        }

    def _get_file_hash(self):
        try:
            return hashlib.md5(self.rules_path.read_bytes()).hexdigest()
        except:
            return None

    def _load_rules(self):
        """仅在文件变化时加载规则"""
        current_hash = self._get_file_hash()
        if current_hash == self._rules_hash and self.rules:
            return

        try:
            with self.rules_path.open('r', encoding='utf-8') as f:
                content = yaml.safe_load(f)
                raw_rules = content.get('rules', []) if content else []
                self.rules = sorted(raw_rules, key=lambda x: x.get('priority', 0), reverse=True)
                
                # 优化点：构建快速匹配字典
                self._keyword_map = {}
                for rule in self.rules:
                    if not rule.get('use_regex') and not rule.get('conditions'):
                        # 只有没有额外复杂条件的规则才进快速通道
                        kw = rule.get('keyword')
                        if kw and kw not in self._keyword_map:
                            self._keyword_map[kw] = rule

                for rule in self.rules:
                    if rule.get('use_regex') and 'keyword' in rule:
                        rule['_regex'] = re.compile(rule['keyword'], re.IGNORECASE)
                
                self._rules_hash = current_hash
                log.info(f"规则库已更新: {self.rules_path} (快速规则: {len(self._keyword_map)})")
        except Exception as e:
            log.error(f"规则库加载失败: {e}")
            if not self.rules: self.rules = []

    def _evaluate_conditions(self, amount, context, conditions):
        """抽象条件匹配逻辑"""
        for cond in conditions:
            field = cond['field']
            field_val = amount if field == 'amount' else context.get(field)
            op_str = cond['operator']
            target_val = cond['value']
            
            if op_str not in self.ops:
                log.warning(f"不支持的运算符: {op_str}")
                return False
                
            if not self.ops[op_str](field_val, target_val):
                return False
        return True

    def reply(self, x: dict = None) -> dict:
        self._load_rules()
        raw_text = str(x.get("content", ""))
        amount = float(x.get("amount", 0))
        trace_id = x.get("trace_id")
        
        category = "待核定"
        confidence = 0.3
        matched_rule_name = "None"
        matched_rule_id = None
        is_gray_rule = False

        # 1. 尝试快速匹配通道 (O(1))
        if raw_text in self._keyword_map:
            rule = self._keyword_map[raw_text]
            category = rule['category']
            confidence = rule.get('confidence', 0.95)
            matched_rule_name = rule.get('keyword')
            matched_rule_id = rule.get('id')
            is_gray_rule = rule.get('audit_level') == 'GRAY'
        else:
            # 2. 传统迭代匹配 (O(N))
            for rule in self.rules:
                is_matched = False
                if rule.get('use_regex') and '_regex' in rule:
                    if rule['_regex'].search(raw_text):
                        is_matched = True
                elif rule.get('keyword') and rule['keyword'] in raw_text:
                    is_matched = True
                    
                if is_matched:
                    if self._evaluate_conditions(amount, x, rule.get('conditions', [])):
                        category = rule['category']
                        for cond in rule.get('conditions', []):
                            if cond.get('category'):
                                category = cond['category']
                        
                        confidence = rule.get('confidence', 0.98)
                        matched_rule_name = rule.get('keyword', 'UnnamedRule')
                        matched_rule_id = rule.get('id')
                        is_gray_rule = rule.get('audit_level') == 'GRAY'
                        break
        
        # 优化点：基于语义与规则权重的多维自动打标 (F3.2.3)
        tags = []
        if is_gray_rule:
            tags.append({"key": "audit_priority", "value": "HIGH"}) # 灰度规则自动提权审计
            
        # 复合打标引擎雏形
        if "项目" in raw_text or "研发" in raw_text:
            tags.append({"key": "dimension", "value": "R&D"})
        if amount > 5000:
            tags.append({"key": "risk_level", "value": "HIGH"})
        if "餐" in raw_text or "食" in raw_text:
            tags.append({"key": "dept", "value": "ADMIN"})

        content = {
            "category": category,
            "confidence": confidence,
            "matched_rule": matched_rule_name,
            "tags": tags,
            # 优化点：灰度敏感标志 (F3.4.2)
            "requires_shadow_audit": is_gray_rule or (confidence < 0.9),
            # 优化点：穿透式推理路径记录 (F3.2.4)
            "inference_log": {
                "raw_text": raw_text,
                "rule_id": matched_rule_id,
                "engine": "L1-Moltbot",
                "is_gray": is_gray_rule,
                "strategy": "FastPath" if raw_text in self._keyword_map else "Iteration"
            }
        }
        
        log.info(f"对账结果: {raw_text[:20]}... -> {category} (Gray: {is_gray_rule})")
        return LedgerMsg.create(self.name, content, action="PROPOSE_ENTRY", trace_id=trace_id)

    def batch_reply(self, items: list) -> list:
        """批量匹配接口，减少重复开销"""
        self._load_rules()
        return [self.reply(item) for item in items]

if __name__ == "__main__":
    agent = AccountingAgent("Test")
    print(agent.reply({"content": "滴滴出行", "amount": 100}).content)
