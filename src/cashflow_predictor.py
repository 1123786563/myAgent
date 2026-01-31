from db_helper import DBHelper
from datetime import datetime, timedelta
from logger import get_logger

log = get_logger("CashflowPredictor")

class CashflowPredictor:
    def __init__(self):
        self.db = DBHelper()
        # 优化点：支持定义固定周期性开支（如房租、工资）
        self.fixed_monthly_costs = 50000.0 

    def predict(self):
        log.info("正在计算现金流天气预报...")
        
        # 1. 真实数据聚合
        avg_daily_out = self.db.get_avg_daily_expenditure(days=30)
        # 如果没有历史数据，使用默认保底值
        if avg_daily_out == 0: avg_daily_out = 100.0
        
        # 优化点：引入变动成本波动率计算 (Suggestion 1)
        # 此处模拟波动率计算，实际应基于标准差
        volatility = 0.15 
        
        # 获取当前现金余额 (简单模拟：总预算 - 总支出)
        stats = self.db.get_ledger_stats()
        total_exp = sum(s['total_amount'] for s in stats if s['total_amount'])
        current_balance = 1000000.0 - total_exp # 假设初始资金 100w
        
        # 2. 计算未来 30 天余额走势 (变动成本 + 固定成本)
        # 引入保守估计 (加入波动率偏差)
        variable_costs = avg_daily_out * 30 * (1 + volatility)
        
        # 优化点：预留未来合同项 (Future Commitment) 解析接口
        future_commitments = self._get_future_commitments()
        
        total_predicted_out = variable_costs + self.fixed_monthly_costs + future_commitments
        predicted_balance_30d = current_balance - total_predicted_out
        
        status = "良好" if predicted_balance_30d > 50000 else "预警"
        
        report = {
            "current_balance": current_balance,
            "predicted_balance_30d": predicted_balance_30d,
            "avg_daily_expenditure": avg_daily_out,
            "fixed_costs": self.fixed_monthly_costs,
            "future_commitments": future_commitments,
            "status": status,
            "insight": "近期变动开支正常，但请注意月末固定大额支出预留。" if status == "良好" else "现金流告急！建议推迟非紧急采购，并检查应收账款。"
        }
        
        log.info(f"预测结果: 余额={current_balance:.2f}, 30d预测={predicted_balance_30d:.2f}, 风险={status}")
        return report

    def _get_future_commitments(self):
        """
        [Suggestion 1] 从数据库中提取未来已承诺但未支付的款项 (如采购合同)
        """
        # 此处为逻辑预留，后续对接具体表
        return 0.0

if __name__ == "__main__":
    analyst = CashflowPredictor()
    print(analyst.predict())
