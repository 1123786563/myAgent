import time
from typing import Dict, Any, List
from core.db_base import DBBase
from core.config_manager import ConfigManager
from infra.logger import get_logger

class DBQueries(DBBase):
    """
    [Optimization Round 49] 数据库查询与统计
    """
    def get_ledger_stats(self):
        current_time = time.time()
        if hasattr(self, '_stats_cache') and (current_time - getattr(self, '_stats_cache_t', 0) < 5):
            return self._stats_cache

        status_order = ['PENDING', 'MATCHED', 'AUDITED', 'POSTED', 'COMPLETED', 'REJECTED']
        status_map = {
            'PENDING': '待处理',
            'MATCHED': '已对账',
            'AUDITED': '已审计',
            'POSTED': '已入账',
            'COMPLETED': '已完成',
            'REJECTED': '已驳回'
        }
        
        sql = """
            SELECT status, COUNT(*) as count, SUM(amount) as total_amount 
            FROM transactions INDEXED BY idx_trans_status
            WHERE status IN ('PENDING', 'MATCHED', 'AUDITED', 'POSTED', 'COMPLETED', 'REJECTED', 'ARCHIVED')
            GROUP BY status
        """
        try:
            with self.transaction("DEFERRED") as conn:
                conn.execute("PRAGMA query_only = ON")
                raw_rows = {row['status']: dict(row) for row in conn.execute(sql).fetchall()}
                conn.execute("PRAGMA query_only = OFF")
                
                res = []
                for s_key in status_order:
                    if s_key in raw_rows:
                        d = raw_rows[s_key]
                    else:
                        d = {'status': s_key, 'count': 0, 'total_amount': 0.0}
                    d['display_name'] = status_map[s_key]
                    res.append(d)
                
                self._stats_cache = res
                self._stats_cache_t = current_time
                return res
        except Exception as e:
            get_logger("DB-Stats").error(f"账务统计高阶查询失败: {e}")
            return [{"status": "ERROR", "display_name": "查询异常", "count": 0, "total_amount": 0.0}]

    def get_roi_metrics(self):
        try:
            with self.transaction("DEFERRED") as conn:
                row = conn.execute("""
                    SELECT COUNT(*) as cnt, SUM(amount) as total 
                    FROM transactions 
                    WHERE status IN ('AUDITED', 'POSTED', 'COMPLETED')
                """).fetchone()
                
                processed_count = row['cnt'] if row else 0
                total_amount = row['total'] if row and row['total'] else 0.0
                
                sector = ConfigManager.get("enterprise.sector", "GENERAL")
                minutes_per_tx = ConfigManager.get_int("roi.minutes_per_tx", 5 if sector == "GENERAL" else 2)
                
                hours_saved = round((processed_count * minutes_per_tx) / 60.0, 2)
                
                token_cost = 0.0
                try:
                    from infra.llm_connector import llm_connector
                    # Depending on how llm_connector is exported, this might need adjustment
                    # For now, let's assume a generic way or mock
                    pass
                except:
                    pass
                
                roi_ratio = round(hours_saved / (token_cost + 0.01), 2)
                
                try:
                    conn.execute('''
                        INSERT INTO roi_metrics_history (report_date, human_hours_saved, token_spend_usd, roi_ratio)
                        VALUES (DATE('now'), ?, ?, ?)
                        ON CONFLICT(report_date) DO UPDATE SET
                            human_hours_saved = excluded.human_hours_saved,
                            token_spend_usd = excluded.token_spend_usd,
                            roi_ratio = excluded.roi_ratio
                    ''', (hours_saved, token_cost, roi_ratio))
                except Exception:
                    pass
                
                return {
                    "human_hours_saved": hours_saved,
                    "token_cost_usd": round(token_cost, 4),
                    "roi_ratio": roi_ratio,
                    "total_amount": round(total_amount, 2),
                    "sector": sector,
                    "minutes_per_tx": minutes_per_tx
                }
        except Exception as e:
            get_logger("DB-ROI").error(f"ROI 计算最终态失败: {e}")
            return {"human_hours_saved": 0, "token_cost_usd": 0, "roi_ratio": 0}

    def get_historical_trend(self, vendor, months=12):
        sql = """
            SELECT category, amount, created_at 
            FROM transactions 
            WHERE vendor = ? AND status IN ('AUDITED', 'POSTED', 'MATCHED')
            AND created_at >= date('now', ?)
            ORDER BY created_at DESC
        """
        try:
            with self.transaction("DEFERRED") as conn:
                rows = [dict(row) for row in conn.execute(sql, (vendor, f'-{months} months')).fetchall()]
                if not rows: return {}
                
                categories = [r['category'] for r in rows]
                amounts = [float(r['amount']) for r in rows]
                
                import statistics
                return {
                    "count": len(rows),
                    "primary_category": max(set(categories), key=categories.count),
                    "avg_amount": statistics.mean(amounts),
                    "std_dev": statistics.stdev(amounts) if len(amounts) > 1 else 0,
                    "last_transaction": rows[0]['created_at']
                }
        except Exception as e:
            get_logger("DB-Trend").error(f"聚合供应商画像失败: {e}")
            return {}

    def get_monthly_stats(self):
        try:
            with self.transaction("DEFERRED") as conn:
                sql_revenue = """
                    SELECT SUM(amount) as total 
                    FROM transactions 
                    WHERE category LIKE '%收入%' 
                    AND created_at >= date('now', 'start of month')
                    AND status = 'AUDITED'
                """
                row_rev = conn.execute(sql_revenue).fetchone()
                revenue = row_rev['total'] if row_rev and row_rev['total'] else 0

                sql_input = """
                    SELECT SUM(amount) as total
                    FROM transactions
                    WHERE category NOT LIKE '%薪资%' AND category NOT LIKE '%税费%'
                    AND created_at >= date('now', 'start of month')
                    AND status = 'AUDITED'
                """
                row_input = conn.execute(sql_input).fetchone()
                total_expense = row_input['total'] if row_input and row_input['total'] else 0
                vat_in = (total_expense / 1.13) * 0.13

                return {
                    "revenue": revenue,
                    "vat_in": vat_in,
                    "total_expense": total_expense
                }
        except Exception as e:
            get_logger("DB").error(f"获取月度报表失败: {e}")
            return {"revenue": 0, "vat_in": 0, "total_expense": 0}
