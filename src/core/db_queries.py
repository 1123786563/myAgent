import time
import json
from typing import Dict, Any, List
from core.db_base import DBBase
from core.config_manager import ConfigManager
from core.db_models import Transaction, ROIMetricsHistory
from infra.logger import get_logger
from sqlalchemy import func, text, or_
from datetime import datetime, timedelta

class DBQueries(DBBase):
    """
    [Optimization Round 49 - SQLAlchemy] 数据库查询与统计
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
        
        try:
            with self.transaction() as session:
                stats = session.query(
                    Transaction.status,
                    func.count(Transaction.id).label('count'),
                    func.sum(Transaction.amount).label('total_amount')
                ).filter(Transaction.status.in_(status_order + ['ARCHIVED'])).group_by(Transaction.status).all()
                
                raw_rows = {s.status: {"status": s.status, "count": s.count, "total_amount": float(s.total_amount or 0)} for s in stats}
                
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
            with self.transaction() as session:
                row = session.query(
                    func.count(Transaction.id).label('cnt'),
                    func.sum(Transaction.amount).label('total')
                ).filter(Transaction.status.in_(['AUDITED', 'POSTED', 'COMPLETED'])).first()
                
                processed_count = row.cnt if row else 0
                total_amount = float(row.total) if row and row.total else 0.0
                
                sector = ConfigManager.get("enterprise.sector", "GENERAL")
                minutes_per_tx = ConfigManager.get_int("roi.minutes_per_tx", 5 if sector == "GENERAL" else 2)
                
                hours_saved = round((processed_count * minutes_per_tx) / 60.0, 2)
                token_cost = 0.0
                roi_ratio = round(hours_saved / (token_cost + 0.01), 2)
                
                # 更新 ROI 历史
                history = session.query(ROIMetricsHistory).filter_by(report_date=datetime.now().date()).first()
                if history:
                    history.human_hours_saved = hours_saved
                    history.token_spend_usd = token_cost
                    history.roi_ratio = roi_ratio
                else:
                    new_roi = ROIMetricsHistory(
                        report_date=datetime.now().date(),
                        human_hours_saved=hours_saved,
                        token_spend_usd=token_cost,
                        roi_ratio=roi_ratio
                    )
                    session.add(new_roi)
                
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
        cache_key = f"trend:{vendor}:{months}"
        now = time.time()
        if hasattr(self, '_trend_cache') and cache_key in self._trend_cache:
            data, expiry = self._trend_cache[cache_key]
            if now < expiry: return data

        try:
            with self.transaction() as session:
                start_date = datetime.now() - timedelta(days=30 * months)
                rows_objs = session.query(Transaction).filter(
                    Transaction.vendor == vendor,
                    Transaction.status.in_(['AUDITED', 'POSTED', 'MATCHED']),
                    Transaction.logical_revert == 0,
                    Transaction.created_at >= start_date
                ).order_by(Transaction.created_at.desc()).all()
                
                if not rows_objs: return {}
                
                rows = []
                for r in rows_objs:
                    rows.append({
                        "id": r.id,
                        "category": r.category,
                        "amount": float(r.amount),
                        "created_at": r.created_at,
                        "inference_log": r.inference_log,
                        "group_id": r.group_id
                    })

                group_ids = [r['group_id'] for r in rows if r['group_id']]
                correlation_summary = ""
                if group_ids:
                    sub_groups = group_ids[:50]
                    # 获取关联供应商
                    corr = session.query(
                        Transaction.vendor,
                        func.count(Transaction.id).label('cnt')
                    ).filter(
                        Transaction.group_id.in_(sub_groups),
                        Transaction.vendor != vendor
                    ).group_by(Transaction.vendor).order_by(text('cnt DESC')).limit(1).first()
                    
                    if corr:
                        prob = corr.cnt / len(rows)
                        correlation_summary = f"关联: {corr.vendor} (置信度 {prob:.1%})"

                categories = [r['category'] for r in rows]
                amounts = [r['amount'] for r in rows]
                
                pattern_summary = ""
                try:
                    dow_stats = {} 
                    month_stats = {}
                    for r in rows:
                        dt = r['created_at']
                        dow = dt.strftime("%A")
                        mon = dt.month
                        dow_stats[dow] = dow_stats.get(dow, 0) + 1
                        month_stats[mon] = month_stats.get(mon, 0) + 1
                    
                    top_dow = max(dow_stats, key=dow_stats.get)
                    if dow_stats[top_dow] / len(rows) > 0.6:
                        pattern_summary = f"规律: 周内{top_dow}"
                    
                    top_mon = max(month_stats, key=month_stats.get)
                    if month_stats[top_mon] / len(rows) > 0.4 and len(rows) > 5:
                        mon_str = f"规律: 年度第{top_mon}月高频"
                        pattern_summary = f"{pattern_summary} | {mon_str}" if pattern_summary else mon_str
                except: pass

                if correlation_summary:
                    pattern_summary = f"{pattern_summary} | {correlation_summary}" if pattern_summary else correlation_summary

                recurrent_tags = []
                for r in rows:
                    if r.get('inference_log'):
                        try:
                            log_obj = r['inference_log']
                            for tag in log_obj.get('tags', []):
                                recurrent_tags.append(f"{tag['key']}:{tag['value']}")
                        except: pass
                
                import statistics
                if recurrent_tags:
                    from collections import Counter
                    common_tags = Counter(recurrent_tags).most_common(1)
                    if common_tags:
                        tag_str = f"高频标签: {common_tags[0][0]}"
                        pattern_summary = f"{pattern_summary} | {tag_str}" if pattern_summary else tag_str

                result = {
                    "count": len(rows),
                    "primary_category": max(set(categories), key=categories.count) if categories else None,
                    "avg_amount": statistics.mean(amounts),
                    "std_dev": statistics.stdev(amounts) if len(amounts) > 1 else 0,
                    "last_transaction": rows[0]['created_at'].strftime("%Y-%m-%d %H:%M:%S"),
                    "pattern_insight": pattern_summary
                }
                
                if not hasattr(self, '_trend_cache'): self._trend_cache = {}
                self._trend_cache[cache_key] = (result, now + 600)
                return result
        except Exception as e:
            get_logger("DB-Trend").error(f"聚合供应商画像失败: {e}")
            return {}

    def get_monthly_stats(self):
        try:
            with self.transaction() as session:
                first_day = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                
                revenue = session.query(func.sum(Transaction.amount)).filter(
                    Transaction.category.like('%收入%'),
                    Transaction.created_at >= first_day,
                    Transaction.status == 'AUDITED'
                ).scalar() or 0

                total_expense = session.query(func.sum(Transaction.amount)).filter(
                    ~Transaction.category.like('%薪资%'),
                    ~Transaction.category.like('%税费%'),
                    Transaction.created_at >= first_day,
                    Transaction.status == 'AUDITED'
                ).scalar() or 0
                
                vat_in = (float(total_expense) / 1.13) * 0.13

                return {
                    "revenue": float(revenue),
                    "vat_in": vat_in,
                    "total_expense": float(total_expense)
                }
        except Exception as e:
            get_logger("DB").error(f"获取月度报表失败: {e}")
            return {"revenue": 0, "vat_in": 0, "total_expense": 0}
