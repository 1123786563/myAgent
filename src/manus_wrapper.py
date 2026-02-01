import uuid
import json
import re
import time
from typing import Dict, Any, List
from bus_init import LedgerMsg
from logger import get_logger
from llm_connector import LLMFactory

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
            # ... (保持原逻辑)

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
        [Round 2] 启动 ReAct 循环
        """
        if not self.cost_control.check_and_record(estimated_cost=0.1):
            return {"category": "MANUAL_REVIEW", "reason": "Cost limit exceeded", "confidence": 0.0}

        history = [f"Task: {task_description}"]
        if context_data:
            history.append(f"Context: {json.dumps(context_data, ensure_ascii=False)}")
            
        history.append("Available Tools: search_web, browser_fetch, ask_user")
        history.append("Format your response as:\nThought: ...\nAction: tool_name(args)\nOR\nFinal Answer: JSON_STRING")

        reasoning_trace = []

        for step in range(self.max_steps):
            prompt = "\n".join(history) + "\n\nBegin Step " + str(step+1)
            
            # 1. LLM Generate
            llm_result = self.llm.generate_response(prompt)
            # generate_response 返回的是结构化 dict，我们需要提取 text 用于 ReAct 解析
            # 这里由于 BaseLLM 接口是针对分类优化的，我们需要稍微 hack 一下或者假定 LLM 能理解 ReAct prompt
            # 实际上 OpenAICompatibleLLM 会返回 {"result": {"category":...}} 这种结构
            # 为了支持 ReAct，我们需要让 LLM 返回自由文本。
            # 这里的改进点是：LLMFactory 应该支持 mode="chat" 而不仅仅是 "classification"
            # 暂时假设 generate_response 的 'reasoning' 字段包含我们需要的内容，或者我们直接修改 prompt 让它把 ReAct 思考过程放在 reasoning 里
            
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