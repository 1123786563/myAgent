import uuid
import json
import re
import time
from typing import Dict, Any, List
from core.bus_init import LedgerMsg
from infra.logger import get_logger
from infra.llm_connector import LLMFactory

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
    [Optimization 4] OpenManus 强推理能力封装
    [Round 2 Optimization] 实现 Agentic ReAct 循环 (Thought -> Action -> Observation)
    """
    def __init__(self):
        self.name = "OpenManusSpecialForce"
        self.cost_control = CostCircuitBreaker(daily_limit_usd=10.0)
        self.llm = LLMFactory.get_llm()
        self.max_steps = 5

    def _execute_tool(self, action_name: str, action_input: str) -> str:
        """
        执行工具调用。目前支持:
        - search_web: 联网搜索 (模拟)
        - browser_fetch: 浏览器抓取 (调用 BrowserBankConnector)
        - ask_user: 询问用户
        - verify_tax_id: 校验纳税人识别号
        """
        log.info(f"[{self.name}] 执行工具: {action_name} | 参数: {action_input}")
        
        if action_name == "search_web":
            # [Optimization Round 9] 更加智能的联网模拟
            if "阿里云" in action_input or "AWS" in action_input:
                return "搜索结果：该供应商属于‘云服务/信息技术基础设施’范畴，常用于技术服务费入账。"
            return f"Search results for '{action_input}': Found relevant business scope info."
            
        elif action_name == "verify_tax_id":
            # 模拟税务校验
            return f"Tax ID '{action_input}' is VALID. Registered as 'General Taxpayer'."
            
        elif action_name == "browser_fetch":
            # 调用 Round 1 实现的 BrowserBankConnector
            try:
                from connectors.browser_bank_connector import BrowserBankConnector
                connector = BrowserBankConnector(bank_name="Shadow-Checking-01")
                # 简单映射：如果 input 是 '7d'，则抓取 7 天
                days = 7
                if "30d" in action_input: days = 30
                
                raw_data = connector.fetch_raw_data(since_time=f"{days}d")
                return f"Browser fetch successful. Retrieved {len(raw_data)} transactions."
            except Exception as e:
                return f"Browser fetch failed: {str(e)}"
                
        elif action_name == "ask_user":
            return "User interaction requested. (Simulated: User provided clarification)"
            
        else:
            return f"Unknown tool: {action_name}"

    def _parse_llm_step(self, response_text: str) -> Dict[str, Any]:
        """
        解析 LLM 返回的 Thought/Action 结构
        期望格式:
        Thought: ...
        Action: tool_name(args)
        """
        thought_match = re.search(r"Thought:\s*(.+)", response_text, re.IGNORECASE)
        action_match = re.search(r"Action:\s*(\w+)\((.+)\)", response_text, re.IGNORECASE)
        
        thought = thought_match.group(1).strip() if thought_match else "Thinking..."
        
        if action_match:
            return {
                "type": "action",
                "thought": thought,
                "tool": action_match.group(1),
                "args": action_match.group(2)
            }
        
        # 如果没有 Action，可能是 Final Answer
        final_match = re.search(r"Final Answer:\s*(.+)", response_text, re.IGNORECASE | re.DOTALL)
        if final_match:
            return {
                "type": "finish",
                "thought": thought,
                "answer": final_match.group(1).strip()
            }
            
        # 兜底：如果是一个 JSON 块，尝试直接解析为结果
        json_match = re.search(r"```json\s*(\{.*?\})\s*```", response_text, re.DOTALL)
        if json_match:
             return {
                "type": "finish",
                "thought": thought,
                "answer": json_match.group(1)
            }

        return {"type": "unknown", "thought": thought, "raw": response_text}

    def investigate(self, task_description: str, context_data: Dict = None) -> Dict[str, Any]:
        """
        [Round 2/31] 启动带动态上下文的 ReAct 循环
        """
        if not self.cost_control.check_and_record(estimated_cost=0.1):
            return {"category": "MANUAL_REVIEW", "reason": "Cost limit exceeded", "confidence": 0.0}

        # [Round 31] 注入更详尽的系统上下文与隐私脱敏
        from core.config_manager import ConfigManager
        sector = ConfigManager.get("enterprise.sector", "GENERAL")
        
        history = [f"System Context: Corporate Sector is {sector}."]
        history.append(f"Task: {task_description}")
        if context_data:
            # 自动过滤 Context 中的敏感信息 (PII)
            from infra.privacy_guard import PrivacyGuard
            guard = PrivacyGuard(role="AGENT_INTERNAL")
            safe_context = {k: (guard.desensitize(v) if isinstance(v, str) else v) for k, v in context_data.items()}
            history.append(f"Sanitized Context: {json.dumps(safe_context, ensure_ascii=False)}")
            
        history.append("Available Tools: search_web, browser_fetch, ask_user, verify_tax_id")
        history.append("Format your response as:\nThought: ...\nAction: tool_name(args)\nOR\nFinal Answer: JSON_STRING")

        reasoning_trace = []

        for step in range(self.max_steps):
            prompt = "\n".join(history) + "\n\nBegin Step " + str(step+1)
            
            # 1. LLM Generate (使用增强的 V2 接口支持上下文)
            llm_result = self.llm.generate_response(prompt, context_params={"sector": sector, "mode": "REASONING"})
            
            response_text = llm_result.get("reasoning", "") + "\n" + json.dumps(llm_result.get("result", {}))
            
            # 尝试解析
            parsed = self._parse_llm_step(response_text)
            
            reasoning_trace.append({
                "step": step + 1,
                "thought": parsed.get("thought"),
                "action": parsed.get("tool"),
                "args": parsed.get("args")
            })
            
            if parsed["type"] == "finish":
                try:
                    # 尝试解析 Final Answer 为 JSON
                    final_json = json.loads(parsed["answer"]) if isinstance(parsed["answer"], str) else parsed["answer"]
                    if not isinstance(final_json, dict):
                         final_json = {"category": "待核定", "reason": str(parsed["answer"])}
                    
                    final_json["reasoning_graph"] = reasoning_trace
                    return final_json
                except:
                    return {
                        "category": "待核定", 
                        "reason": parsed["answer"], 
                        "confidence": 0.5,
                        "reasoning_graph": reasoning_trace
                    }
            
            elif parsed["type"] == "action":
                # 2. Execute Action
                observation = self._execute_tool(parsed["tool"], parsed["args"])
                history.append(f"Observation: {observation}")
                
            else:
                # Unknown response, force termination or retry
                history.append("System: Invalid format. Please Output 'Final Answer: JSON' or 'Action: tool(arg)'")

        return {
            "category": "超时未决", 
            "reason": "Max steps reached without conclusion", 
            "confidence": 0.0,
            "reasoning_graph": reasoning_trace
        }

if __name__ == "__main__":
    analyst = OpenManusAnalyst()
    print(analyst.investigate("分析这笔交易: 收到一张玄铁重剑的发票，金额 500 元"))
