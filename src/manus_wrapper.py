import uuid
import json
import re
from bus_init import LedgerMsg
from logger import get_logger

log = get_logger("OpenManusWrapper")

class CostCircuitBreaker:
    """[Suggestion 3] 成本熔断器"""
    def __init__(self, daily_limit_usd=5.0):
        self.daily_limit = daily_limit_usd
        self.current_spend = 0.0

    def check_and_record(self, estimated_cost):
        if self.current_spend + estimated_cost > self.daily_limit:
            log.warning(f"OpenManus 熔断: 今日花费 {self.current_spend:.2f} + {estimated_cost:.2f} > 限额 {self.daily_limit}")
            return False
        self.current_spend += estimated_cost
        return True

class OpenManusAnalyst:
    """
    [Optimization 4] 模拟 OpenManus 的强推理能力与安全沙箱执行 (F3.1.4)
    """
    def __init__(self):
        self.name = "OpenManusSpecialForce"
        self.cost_control = CostCircuitBreaker(daily_limit_usd=10.0) # $10 limit

    def _run_in_sandbox(self, task_name, payload):
        """
        [Optimization 4] 安全沙箱执行层
        模拟无状态子进程隔离执行，完成后立即擦除敏感数据
        """
        log_info = f"[{self.name}] 正在启动无状态沙箱: {task_name}"
        print(log_info)
        # 实际实现将使用 os.fork() 或 docker sdk
        try:
            # 模拟抓取逻辑
            return {"status": "SUCCESS", "data": "BANK_FLOW_EXTRACTED"}
        finally:
            print(f"[{self.name}] 沙箱已物理销毁，凭据已擦除。")

    def _safe_parse_output(self, llm_response):
        """[Suggestion 4] 弹性输出解析器 (Resilient Parsing)"""
        # 尝试 JSON 解析
        try:
            return json.loads(llm_response)
        except json.JSONDecodeError:
            pass
            
        # 尝试从 Markdown 代码块提取
        match = re.search(r"```json\s*(\{.*?\})\s*```", llm_response, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except:
                pass
                
        # 兜底：关键词正则提取
        category_match = re.search(r"category[\"']?:\s*[\"'](.*?)[\"']", llm_response)
        confidence_match = re.search(r"confidence[\"']?:\s*(\d+\.?\d*)", llm_response)
        
        return {
            "category": category_match.group(1) if category_match else "待核定",
            "confidence": float(confidence_match.group(1)) if confidence_match else 0.5,
            "reason": "Parsed via fallback regex"
        }

    def investigate(self, raw_data_context, group_context=None, history_trend=None):
        """
        [Optimization 2] 增强型多模态聚合调查 (F3.1.3)
        [Optimization 4] 结构化推理图存证 (F3.2.4)
        """
        # [Suggestion 3] 成本预检
        if not self.cost_control.check_and_record(estimated_cost=0.05):
            return {"category": "MANUAL_REVIEW", "reason": "Cost limit exceeded", "confidence": 0.0}

        context_payload = f"【当前单据】: {raw_data_context}\n"
        
        # 记录推理初始步骤
        reasoning_steps = [
            {"step": 1, "action": "INITIAL_CONTEXT_LOAD", "result": "Loaded current receipt data"}
        ]
        
        if group_context:
            print(f"[{self.name}] 正在执行多模态资产画像聚合 (Size: {len(group_context)})")
            # 聚合多角度视觉描述与元数据 (Optimization 2)
            group_summary = group_context.get('visual_summary', '')
            context_payload += f"【关联多角度视觉描述】: {group_summary}\n"
            reasoning_steps.append({"step": 2, "action": "ASSET_IMAGE_AGGREGATION", "result": f"Merged {len(group_context)} image summaries"})

        if history_trend:
            print(f"[{self.name}] 正在注入 12 个月供应商历史趋势画像")
            # 注入均值、常用科目等信息帮助识别离群值
            context_payload += f"【历史画像摘要】: 常入科目={history_trend.get('primary_category')}, 月均交易={history_trend.get('avg_amount'):.2f}\n"
            reasoning_steps.append({"step": 3, "action": "HISTORICAL_PROFILE_MATCH", "result": "Calculated consistency with vendor profile"})

        print(f"[{self.name}] 正在启动 L2 强推理 (Reasoning Graph Mode)...")
        
        # [Suggestion 5] 双向反查回路
        if "未知物品" in context_payload:
             return {
                 "action": "ASK_USER",
                 "question": "无法识别该物品。请提供照片或说明用途。",
                 "confidence": 0.0
             }

        # 模拟 LLM 响应 (包含杂音)
        llm_raw_response = """
        I have analyzed the receipt.
        ```json
        {
            "category": "办公费用-福利费",
            "reason": "多模态核实：经照片比对确认属于员工福利实物。",
            "confidence": 0.99
        }
        ```
        """
        
        # 使用安全解析器
        parsed_result = self._safe_parse_output(llm_raw_response)
        parsed_result["reasoning_graph"] = reasoning_steps
        
        return parsed_result

if __name__ == "__main__":
    analyst = OpenManusAnalyst()
    print(analyst.investigate("收到一张玄铁重剑的发票，金额 500 元"))
