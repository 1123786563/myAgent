import uuid
from bus_init import LedgerMsg

class OpenManusAnalyst:
    """
    [Optimization 4] 模拟 OpenManus 的强推理能力与安全沙箱执行 (F3.1.4)
    """
    def __init__(self):
        self.name = "OpenManusSpecialForce"

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

    def investigate(self, raw_data_context, group_context=None, history_trend=None):
        """
        [Optimization 2] 增强型多模态聚合调查 (F3.1.3)
        [Optimization 4] 结构化推理图存证 (F3.2.4)
        """
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
        # 模拟决策逻辑 (Reasoning Graph Mode)
        if "玄铁重剑" in context_payload:
            reasoning_steps.append({"step": 4, "action": "TAX_POLICY_COMPLIANCE", "result": "Verified asset threshold (2000 CNY)"})
            return {
                "category": "办公费用-福利费",
                "reason": "多模态核实：经照片比对确认属于员工福利实物，且单价符合该供应商历史波动范围。",
                "confidence": 0.99,
                "reasoning_graph": reasoning_steps # [Optimization 4]
            }
        
        reasoning_steps.append({"step": 4, "action": "FALLBACK", "result": "Confidence below threshold"})
        return {"category": "待核定", "confidence": 0.1, "reasoning_graph": reasoning_steps}

if __name__ == "__main__":
    analyst = OpenManusAnalyst()
    print(analyst.investigate("收到一张玄铁重剑的发票，金额 500 元"))
