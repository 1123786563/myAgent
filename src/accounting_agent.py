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
from config_manager import ConfigManager

log = get_logger("AccountingAgent")

class AccountingAgent(AgentBase):
    def __init__(self, name, rules_path=None):
        super().__init__(name=name)
        self.rules_path = Path(rules_path or get_path("src", "accounting_rules.yaml"))
        self.rules = []
        self._rules_hash = None
        self.db = None # Will be initialized or accessed via DBHelper singleton
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
                
                # 构建快速匹配字典
                self._keyword_map = {}
                for rule in self.rules:
                    if not rule.get('use_regex') and not rule.get('conditions'):
                        kw = rule.get('keyword')
                        if kw and kw not in self._keyword_map:
                            self._keyword_map[kw] = rule

                for rule in self.rules:
                    if rule.get('use_regex') and 'keyword' in rule:
                        rule['_regex'] = re.compile(rule['keyword'], re.IGNORECASE)
                
                self._rules_hash = current_hash
                log.info(f"规则库已更新: {self.rules_path}")
        except Exception as e:
            log.error(f"规则库加载失败: {e}")
            if not self.rules: self.rules = []

    def _evaluate_conditions(self, amount, context, conditions):
        for cond in conditions:
            field = cond['field']
            field_val = amount if field == 'amount' else context.get(field)
            op_str = cond['operator']
            target_val = cond['value']
            if op_str not in self.ops: continue
            if not self.ops[op_str](field_val, target_val):
                return False
        return True

    def _semantic_match(self, text):
        """[Optimization 1] 语义相似度探测 (F3.2.1)"""
        text_set = set(re.findall(r'\w+', text.lower()))
        best_rule, max_overlap = None, 0
        for rule in self.rules:
            kw = rule.get('keyword', '').lower()
            kw_set = set(re.findall(r'\w+', kw))
            if not kw_set: continue
            overlap = len(text_set & kw_set) / (len(kw_set) + 1e-9)
            if overlap > 0.7 and overlap > max_overlap:
                max_overlap = overlap
                best_rule = rule
        return best_rule, max_overlap

    def _extract_semantic_dimensions(self, text, amount):
        """[Optimization 1] 语义维度结构化提取 (F3.2.3)"""
        dimensions = {}
        if any(k in text for k in ["研发", "项目", "迭代"]):
            dimensions["accounting_type"] = "CAPITAL_EXPENDITURE" if amount > 5000 else "OPERATING_EXPENSE"
        
        dept_rules = {"R&D": r"服务器|测试|AWS", "SALES": r"招待|礼品", "ADMIN": r"办公|房租"}
        for dept, pat in dept_rules.items():
            if re.search(pat, text):
                dimensions["department_ref"] = dept
                break
        return dimensions

    def reply(self, x: dict = None) -> dict:
        from db_helper import DBHelper
        self.db = DBHelper()
        self._load_rules()
        raw_text = str(x.get("content", ""))
        amount = float(x.get("amount", 0))
        vendor = x.get("vendor", "Unknown")
        trace_id = x.get("trace_id")
        
        # 1. 动态路由预检 (Expert Routing)
        from routing_registry import RoutingRegistry
        registry = RoutingRegistry()
        route = registry.get_route(raw_text, vendor=vendor)
        if "L2" in route:
             log.info(f"动态路由拦截 -> 强制升级 L2 | TraceID={trace_id}")
             x['requires_upgrade'] = True

        # 2. 注入历史画像 Context (Long-Context Injection)
        history_summary = self.db.get_historical_trend(vendor)
        if history_summary:
            x['historical_context'] = history_summary

        # 3. 分类逻辑 (L1)
        category, confidence = "待核定", 0.3
        matched_rule_id = None
        is_gray = False
        tags = []

        # 快速通道
        if raw_text in self._keyword_map:
            rule = self._keyword_map[raw_text]
            category, confidence = rule['category'], rule.get('confidence', 0.95)
            matched_rule_id, is_gray = rule.get('id'), rule.get('audit_status') == 'GRAY'
        else:
            # 语义匹配
            rule, score = self._semantic_match(raw_text)
            if rule and score > 0.8:
                category, confidence = rule['category'], score * 0.95
                matched_rule_id = rule.get('id')
            else:
                # 迭代正则匹配
                for rule in self.rules:
                    if (rule.get('use_regex') and rule.get('_regex') and rule['_regex'].search(raw_text)) or \
                       (not rule.get('use_regex') and rule.get('keyword') and rule['keyword'] in raw_text):
                        if self._evaluate_conditions(amount, x, rule.get('conditions', [])):
                            category, confidence = rule['category'], rule.get('confidence', 0.98)
                            # 条件覆盖
                            for cond in rule.get('conditions', []):
                                if cond.get('category'): category = cond['category']
                            matched_rule_id = rule.get('id')
                            break

        # 4. 维度提取与打标 (Optimization 1)
        semantic_dims = self._extract_semantic_dimensions(raw_text, amount)
        for k, v in semantic_dims.items():
            tags.append({"key": k, "value": v})

        # 项目打标
        project_match = re.search(r"项目[:：]?\s*([a-zA-Z0-9_\u4e00-\u9fa5]+)", raw_text)
        if project_match:
            tags.append({"key": "project_id", "value": project_match.group(1)})

        # [Optimization 2] 构建结构化思维链 (Chain of Thought)
        inference_steps = [
            {"step": "INPUT_ANALYSIS", "details": f"Vendor: {vendor}, Amount: {amount}, Text: {raw_text[:20]}..."},
            {"step": "ROUTING", "result": "L1_FAST" if matched_rule_id else "L1_SEMANTIC"},
            {"step": "RULE_MATCH", "rule_id": matched_rule_id, "match_type": "KEYWORD" if raw_text in self._keyword_map else "SEMANTIC/REGEX"},
            {"step": "DIMENSION_EXTRACTION", "dims": semantic_dims},
            {"step": "CONFIDENCE_SCORING", "score": confidence}
        ]

        content = {
            "category": category,
            "confidence": confidence,
            "tags": tags,
            "requires_shadow_audit": is_gray or (confidence < 0.9),
            "inference_log": {
                "engine": "L1-Moltbot",
                "cot_trace": inference_steps, # 完整的思维链
                "rule_id": matched_rule_id
            }
        }
        
        log.info(f"分类结果: {vendor} -> {category} (Conf: {confidence:.2f})")
        registry.record_feedback(vendor, confidence) # 自学习反馈
        
        return LedgerMsg.create(self.name, content, action="PROPOSE_ENTRY", trace_id=trace_id, sender_role="ACCOUNTANT")

    def batch_reply(self, items: list) -> list:
        self._load_rules()
        return [self.reply(item) for item in items]
