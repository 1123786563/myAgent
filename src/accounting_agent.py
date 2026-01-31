import yaml
import re
import os
import hashlib
import operator
import threading
import time
from pathlib import Path
from bus_init import LedgerMsg
from agentscope.agents import AgentBase
from logger import get_logger
from project_paths import get_path
from config_manager import ConfigManager
from db_helper import DBHelper

from llm_connector import LLMFactory

log = get_logger("AccountingAgent")


class AccountingAgent(AgentBase):
    def __init__(self, name, rules_path=None):
        super().__init__(name=name)
        self.rules_path = Path(rules_path or get_path("src", "accounting_rules.yaml"))
        self.rules = []
        self._rules_hash = None
        self.db = None  # Will be initialized or accessed via DBHelper singleton
        self._load_rules()

        # 逻辑运算符映射
        self.ops = {
            ">": operator.gt,
            "<": operator.lt,
            "==": operator.eq,
            ">=": operator.ge,
            "<=": operator.le,
            "in": lambda x, y: x in y if isinstance(y, (list, str)) else False,
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
            with self.rules_path.open("r", encoding="utf-8") as f:
                content = yaml.safe_load(f)
                raw_rules = content.get("rules", []) if content else []
                self.rules = sorted(
                    raw_rules, key=lambda x: x.get("priority", 0), reverse=True
                )

                # 构建快速匹配字典
                self._keyword_map = {}
                for rule in self.rules:
                    if not rule.get("use_regex") and not rule.get("conditions"):
                        kw = rule.get("keyword")
                        if kw and kw not in self._keyword_map:
                            self._keyword_map[kw] = rule

                for rule in self.rules:
                    if rule.get("use_regex") and "keyword" in rule:
                        rule["_regex"] = re.compile(rule["keyword"], re.IGNORECASE)

                self._rules_hash = current_hash
                log.info(f"规则库已更新: {self.rules_path}")
        except Exception as e:
            log.error(f"规则库加载失败: {e}")
            if not self.rules:
                self.rules = []

    def _evaluate_conditions(self, amount, context, conditions):
        for cond in conditions:
            field = cond["field"]
            field_val = amount if field == "amount" else context.get(field)
            op_str = cond["operator"]
            target_val = cond["value"]
            if op_str not in self.ops:
                continue
            if not self.ops[op_str](field_val, target_val):
                return False
        return True

    def _semantic_match(self, text):
        """[Optimization 1] 语义相似度探测 (F3.2.1)"""
        text_set = set(re.findall(r"\w+", text.lower()))
        best_rule, max_overlap = None, 0
        for rule in self.rules:
            kw = rule.get("keyword", "").lower()
            kw_set = set(re.findall(r"\w+", kw))
            if not kw_set:
                continue
            overlap = len(text_set & kw_set) / (len(kw_set) + 1e-9)
            if overlap > 0.7 and overlap > max_overlap:
                max_overlap = overlap
                best_rule = rule
        return best_rule, max_overlap

    def _extract_semantic_dimensions(self, text, amount):
        """[Optimization 1] 语义维度结构化提取 (F3.2.3)"""
        dimensions = {}
        if any(k in text for k in ["研发", "项目", "迭代"]):
            dimensions["accounting_type"] = (
                "CAPITAL_EXPENDITURE" if amount > 5000 else "OPERATING_EXPENSE"
            )

        dept_rules = {
            "R&D": r"服务器|测试|AWS",
            "SALES": r"招待|礼品",
            "ADMIN": r"办公|房租",
        }
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
            x["requires_upgrade"] = True

        # 2. 注入历史画像 Context (Long-Context Injection)
        history_summary = self.db.get_historical_trend(vendor)
        if history_summary:
            x["historical_context"] = history_summary

        # 3. 分类逻辑 (L1)
        category, confidence = "待核定", 0.3
        matched_rule_id = None
        is_gray = False
        tags = []

        # 快速通道
        if raw_text in self._keyword_map:
            rule = self._keyword_map[raw_text]
            category, confidence = rule["category"], rule.get("confidence", 0.95)
            matched_rule_id, is_gray = (
                rule.get("id"),
                rule.get("audit_status") == "GRAY",
            )
        else:
            # 语义匹配
            rule, score = self._semantic_match(raw_text)
            if rule and score > 0.8:
                category, confidence = rule["category"], score * 0.95
                matched_rule_id = rule.get("id")
            else:
                # 迭代正则匹配
                for rule in self.rules:
                    if (
                        rule.get("use_regex")
                        and rule.get("_regex")
                        and rule["_regex"].search(raw_text)
                    ) or (
                        not rule.get("use_regex")
                        and rule.get("keyword")
                        and rule["keyword"] in raw_text
                    ):
                        if self._evaluate_conditions(
                            amount, x, rule.get("conditions", [])
                        ):
                            category, confidence = (
                                rule["category"],
                                rule.get("confidence", 0.98),
                            )
                            # 条件覆盖
                            for cond in rule.get("conditions", []):
                                if cond.get("category"):
                                    category = cond["category"]
                            matched_rule_id = rule.get("id")
                            break

        # 4. 维度提取与打标 (Optimization 1)
        semantic_dims = self._extract_semantic_dimensions(raw_text, amount)
        for k, v in semantic_dims.items():
            tags.append({"key": k, "value": v})

        # 项目打标
        project_match = re.search(
            r"项目[:：]?\s*([a-zA-Z0-9_\u4e00-\u9fa5]+)", raw_text
        )
        if project_match:
            tags.append({"key": "project_id", "value": project_match.group(1)})

        # [Optimization 2] 构建结构化思维链 (Chain of Thought)
        inference_steps = [
            {
                "step": "INPUT_ANALYSIS",
                "details": f"Vendor: {vendor}, Amount: {amount}, Text: {raw_text[:20]}...",
            },
            {
                "step": "ROUTING",
                "result": "L1_FAST" if matched_rule_id else "L1_SEMANTIC",
            },
            {
                "step": "RULE_MATCH",
                "rule_id": matched_rule_id,
                "match_type": "KEYWORD"
                if raw_text in self._keyword_map
                else "SEMANTIC/REGEX",
            },
            {"step": "DIMENSION_EXTRACTION", "dims": semantic_dims},
            {"step": "CONFIDENCE_SCORING", "score": confidence},
        ]

        content = {
            "category": category,
            "confidence": confidence,
            "tags": tags,
            "requires_shadow_audit": is_gray or (confidence < 0.9),
            "inference_log": {
                "engine": "L1-Moltbot",
                "cot_trace": inference_steps,  # 完整的思维链
                "rule_id": matched_rule_id,
            },
        }

        log.info(f"分类结果: {vendor} -> {category} (Conf: {confidence:.2f})")
        registry.record_feedback(vendor, confidence)  # 自学习反馈

        return LedgerMsg.create(
            self.name,
            content,
            action="PROPOSE_ENTRY",
            trace_id=trace_id,
            sender_role="ACCOUNTANT",
        )

    def batch_reply(self, items: list) -> list:
        self._load_rules()
        return [self.reply(item) for item in items]


class RecoveryWorker(threading.Thread):
    """
    [Optimization 4] 自愈工作线程 (Self-Healing Worker)
    负责扫描被审计驳回的单据，并升级到 L2 (OpenManus) 进行重试
    """

    def __init__(self, agent):
        super().__init__(daemon=True, name="Accounting-Recovery")
        self.agent = agent
        self.db = DBHelper()

    def run(self):
        log.info("RecoveryWorker 启动: 监听 REJECTED 队列...")
        while True:
            try:
                # 1. 扫描被驳回的交易
                with self.db.transaction("DEFERRED") as conn:
                    # 查找最近 24 小时内被驳回且未尝试过恢复的记录
                    sql = """
                        SELECT id, vendor, amount, inference_log 
                        FROM transactions 
                        WHERE status = 'REJECTED' 
                        AND created_at > datetime('now', '-1 day')
                        AND inference_log NOT LIKE '%RECOVERY_ATTEMPT%'
                    """
                    tasks = conn.execute(sql).fetchall()

                for task in tasks:
                    self._attempt_recovery(dict(task))

                time.sleep(60)  # 每分钟扫描一次
            except Exception as e:
                log.error(f"自愈扫描异常: {e}")
                time.sleep(60)

    def _attempt_recovery(self, task):
        tid = task["id"]
        vendor = task["vendor"] or ""
        amount = float(task["amount"])
        log.info(f"正在尝试修复交易 {tid} (Vendor: {vendor})...")

        new_category = "待人工确认"
        reason = "L2无法确定"
        confidence = 0.0

        try:
            # [Optimization] Use LLMConnector to simulate OpenManus autonomous reasoning
            # instead of simple regex matching.
            llm = LLMFactory.get_llm("MOCK")
            prompt = f"Analyze vendor '{vendor}' with amount {amount}. Classify into accounting category."

            response = llm.generate_response(prompt)

            result = response.get("result", {})
            new_category = result.get("category", "待人工确认")
            reason = f"L2 AI Reasoning: {result.get('reason', 'Unknown')}"
            confidence = response.get("confidence", 0.0)

            log.info(f"L2 reasoning result: {new_category} (Conf: {confidence})")

        except Exception as e:
            log.error(f"L2 Reasoning Error: {e}")

        # Fallback logic if KB fails but amount is tiny
        if confidence == 0.0 and amount < 50:
            new_category = "杂项费用"
            reason = "L2 Micro-Payment Waiver"
            confidence = 0.7

        # 更新数据库
        try:
            with self.db.transaction("IMMEDIATE") as conn:
                import json

                old_log = task["inference_log"]
                new_log_entry = {
                    "step": "RECOVERY_ATTEMPT",
                    "l2_decision": new_category,
                    "reason": reason,
                    "confidence": confidence,
                    "engine": "L2-OpenManus-Sim",  # Updated engine name
                    "raw_llm_response": response if "response" in locals() else {},
                }

                # 尝试追加日志
                try:
                    log_obj = json.loads(old_log) if old_log else {}
                    if "recovery_trace" not in log_obj:
                        log_obj["recovery_trace"] = []
                    log_obj["recovery_trace"].append(new_log_entry)
                    final_log = json.dumps(log_obj, ensure_ascii=False)
                except:
                    final_log = str(old_log) + " | RECOVERY: " + str(new_log_entry)

                conn.execute(
                    """
                    UPDATE transactions 
                    SET category = ?, status = 'PENDING_AUDIT', inference_log = ? 
                    WHERE id = ?
                """,
                    (new_category, final_log, tid),
                )

            log.info(
                f"交易 {tid} 修复成功 -> {new_category} (Reason: {reason})，已重新提交审计。"
            )
        except Exception as e:
            log.error(f"交易 {tid} 修复失败: {e}")


if __name__ == "__main__":
    import threading
    import time
    from graceful_exit import should_exit

    agent = AccountingAgent("Accounting-Master")
    worker = RecoveryWorker(agent)
    worker.start()

    log.info("AccountingAgent 服务已启动 (包含自愈模块)...")

    # 模拟服务循环，处理来自 Bus 的请求 (此处仅为占位，实际需对接 MQ 或 DB 轮询)
    while not should_exit():
        time.sleep(5)
