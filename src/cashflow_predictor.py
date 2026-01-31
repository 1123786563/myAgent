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
        log.info("正在计算增强型现金流天气预报 (Weather Forecast)...")
        
        # 1. 基础数据聚合
        avg_daily_out = self.db.get_avg_daily_expenditure(days=30)
        if avg_daily_out == 0: avg_daily_out = 100.0
        
        # [Optimization 5] 引入历史季节性权重 (F3.3.3)
        # 逻辑：识别季度末（3, 6, 9, 12月），通常支出会增加 30%
        seasonality_factor = 1.0
        month = datetime.now().month
        if month in (3, 6, 9, 12):
            seasonality_factor = 1.3
            log.info(f"检测到季度末季节性因素，风险修正系数: {seasonality_factor}")
        
        # 获取当前现金余额 (模拟)
        current_balance = 100000.0 
        
        # 2. 计算未来 30 天预测
        total_predicted_out = avg_daily_out * 30 * seasonality_factor + self.fixed_monthly_costs
        predicted_balance_30d = current_balance - total_predicted_out
        
        # [Optimization 3] 现金流耗尽点 (Burnout Point) 计算
        days_until_burnout = current_balance / (avg_daily_out * seasonality_factor + 1)
        
        # 风险定级逻辑
        status = "良好"
        is_alarm = False
        if predicted_balance_30d < 10000 or days_until_burnout < 7:
            status = "极度危险"
            is_alarm = True
        elif predicted_balance_30d < 30000:
            status = "橙色预警"
            
        report = {
            "current_balance": current_balance,
            "predicted_balance_30d": predicted_balance_30d,
            "days_until_burnout": round(days_until_burnout, 1),
            "seasonality_factor": seasonality_factor,
            "status": status,
            "is_alarm": is_alarm,
            "insight": self._generate_insight(status, predicted_balance_30d, total_predicted_out)
        }
        
        if is_alarm:
            log.critical(f"现金流告警！耗尽点预计在 {days_until_burnout:.1f} 天后到达。")
        
        log.info(f"预测完成: 30天后预计余额 ￥{predicted_balance_30d:.2f} ({status})")
        return report

    def _get_future_commitments_from_db(self):
        """
        从数据库查询待付合同款项 (模拟)
        """
        # 真实逻辑会查询 transactions 表中状态为 'PENDING_PAYMENT' 的记录
        return 12000.0 

    def _generate_insight(self, status, balance, commitments):
        if status == "良好":
            return "现金流充沛。建议考虑将闲置资金配置为短期理财，或提前支付部分供应商合同以换取折扣。"
        elif status == "预警":
            return f"注意！预计 30 天后余额将降至 ￥{balance:.2f}。建议核查未来 ￥{commitments:.2f} 的待付合同，优化支出结构。"
        else:
            return "极度危险！现金耗尽点即将来临。请立即冻结非必要开支，并联系客户催收账款。"

if __name__ == "__main__":
    analyst = CashflowPredictor()
    print(analyst.predict())
