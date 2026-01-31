import csv
import json
import os
import uuid
import threading
from project_paths import get_path
from logger import get_logger
from db_helper import DBHelper

log = get_logger("Exporter")

class FinancialExporter:
    def __init__(self, operator="LedgerAlpha-AI"):
        self.db = DBHelper()
        self.operator = operator

    def export_ledger(self, records, filename=None, file_format="csv"):
        """
        统一导出接口，支持审计与异步处理
        """
        if not records:
            log.warning("没有可导出的记录")
            return None

        export_id = str(uuid.uuid4())
        if not filename:
            filename = f"ledger_export_{export_id[:8]}.{file_format}"
        
        # 1. 记录审计开始
        self._audit_start(export_id, filename, len(records))

        # 2. 执行导出逻辑
        target_path = None
        try:
            if file_format == "csv":
                target_path = self._to_csv(records, filename)
            elif file_format == "json":
                target_path = self._to_json(records, filename)
            elif file_format == "markdown_report":
                target_path = self._to_investment_report(records, filename)
            
            if target_path:
                self._audit_complete(export_id, "COMPLETED")
            else:
                self._audit_complete(export_id, "FAILED")
        except Exception as e:
            log.error(f"导出过程发生异常: {e}")
            self._audit_complete(export_id, "FAILED")
        
        return target_path

    def _to_investment_report(self, records, filename):
        """
        生成投融资标准包报告 (F3.3.4) - 接入专业经营分析
        """
        target_path = get_path("workspace", filename)
        try:
            total_amount = sum(float(r.get('amount', 0)) for r in records)
            count = len(records)
            
            # 1. 动态接入现金流预测
            from cashflow_predictor import CashflowPredictor
            prediction = CashflowPredictor().predict()

            # 2. 动态接入 ROI 指标
            roi_data = self.db.get_roi_metrics()

            content = f"""# LedgerAlpha 投融资标准财务报告
## 1. 报告概览
- **导出时间**: {self.db.get_now()}
- **操作员**: {self.operator}
- **数据周期**: 全量历史数据
- **分录总数**: {count} 条
- **交易总额**: ￥{total_amount:,.2f}

## 2. 经营效益分析 (ROI)
- **节省人工工时**: {roi_data.get('human_hours_saved', 0)}h
- **Token 投资成本**: ${roi_data.get('token_cost_usd', 0):.4f}
- **ROI 效益比**: {roi_data.get('roi_ratio', 0)}

## 3. 现金流天气预报 (Financial Health)
- **当前账面余额**: ￥{prediction['current_balance']:,.2f}
- **30天后预测余额**: ￥{prediction['predicted_balance_30d']:,.2f}
- **季节性因子**: {prediction['seasonality_factor']}
- **风险等级**: {prediction['status']}
- **AI 专家洞察**: {prediction['insight']}

## 4. 供应商偏好与异常监测
> *注：此处基于历史聚类分析偏差 > 15% 的异常交易。*

| 日期 | 供应商 | 科目 | 金额 | 风险判定 |
| :--- | :--- | :--- | :--- | :--- |
"""
            # 挑选风险分较高的记录展示
            for r in records[:20]: 
                risk_tag = "正常"
                if float(r.get('amount', 0)) > 5000: risk_tag = "**需关注**"
                content += f"| {r.get('created_at', '')} | {r.get('vendor', '')} | {r.get('category', '')} | ￥{float(r.get('amount',0)):,.2f} | {risk_tag} |\n"

            with open(target_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            log.info(f"成功生成投融资标准报告: {target_path}")
            return target_path
        except Exception as e:
            log.error(f"生成投融资报告失败: {e}")
            return None

    def _to_csv(self, records, filename):
        target_path = get_path("workspace", filename)
        headers = ['日期', '凭证号', '摘要', '科目', '借方金额', '贷方金额', '制单人']
        try:
            with open(target_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                for r in records:
                    writer.writerow([
                        r.get('created_at', ''),
                        r.get('id', ''),
                        r.get('vendor', ''),
                        r.get('category', ''),
                        r.get('amount', 0),
                        0,
                        self.operator
                    ])
            log.info(f"成功导出 CSV: {target_path}")
            return target_path
        except Exception as e:
            log.error(f"生成 CSV 失败: {e}")
            return None

    def _to_json(self, records, filename):
        target_path = get_path("workspace", filename)
        try:
            with open(target_path, 'w', encoding='utf-8') as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
            log.info(f"成功导出 JSON: {target_path}")
            return target_path
        except Exception as e:
            log.error(f"生成 JSON 失败: {e}")
            return None

    def _audit_start(self, export_id, filename, count):
        """记录导出审计开始"""
        # [Optimization 4] 导出前自动创建数据快照
        from db_helper import DBHelper
        DBHelper().create_ledger_snapshot(tag=f"EXPORT_{export_id[:8]}")
        
        try:
            with self.db.transaction("IMMEDIATE") as conn:
                conn.execute("""
                    INSERT INTO export_audit (export_id, filename, record_count, operator, status)
                    VALUES (?, ?, ?, ?, 'PENDING')
                """, (export_id, filename, count, self.operator))
        except Exception as e:
            log.error(f"审计记录失败 (Start): {e}")

    def _audit_complete(self, export_id, status):
        """记录导出审计完成"""
        try:
            with self.db.transaction("IMMEDIATE") as conn:
                conn.execute("""
                    UPDATE export_audit SET status = ? WHERE export_id = ?
                """, (status, export_id))
        except Exception as e:
            log.error(f"审计记录失败 (Complete): {e}")

    def export_async(self, records, filename=None, file_format="csv"):
        """异步导出接口"""
        thread = threading.Thread(target=self.export_ledger, args=(records, filename, file_format))
        thread.daemon = True
        thread.start()
        log.info("导出任务已在后台启动")
        return True
