import time
import threading
import queue
import json
from difflib import SequenceMatcher
from decimal import Decimal
from core.db_helper import DBHelper
from core.db_models import Transaction, PendingEntry
from utils.decimal_utils import to_decimal
from infra.logger import get_logger
from core.config_manager import ConfigManager
from sqlalchemy import func, text

log = get_logger("MatchEngine")

class MatchStrategy:
    """对账匹配策略封装"""
    @staticmethod
    def is_amount_match(a, b, tolerance=0.01):
        return abs(a - b) < tolerance

    @staticmethod
    def get_fuzzy_ratio(s1, s2):
        if not s1 or not s2: return 0
        return SequenceMatcher(None, s1.lower(), s2.lower()).ratio()

class MatchEngine:
    def __init__(self):
        self.db = DBHelper()
        self.batch_size = 100
        self.time_window_days = 7
        self.fuzzy_threshold = 0.8
        self.worker_count = ConfigManager.get("match_engine.worker_count", 4)
        self.task_queue = queue.Queue(maxsize=self.batch_size)

    def _match_worker(self):
        """并发匹配工作者线程"""
        while True:
            task = self.task_queue.get()
            if task is None: break
            
            shadow_data, potential_matches = task
            try:
                best_match = None
                max_score = 0.0
                
                for c in potential_matches:
                    score = MatchStrategy.get_fuzzy_ratio(shadow_data['vendor_keyword'], c['vendor'])
                    
                    if c['status'] != 'MATCHED':
                        score += 0.1
                        
                    if score > self.fuzzy_threshold and score > max_score:
                        max_score = score
                        best_match = c
                
                if best_match:
                    log.info(f"消消乐并行匹配成功 (Score: {max_score:.2f}): {shadow_data['vendor_keyword']} <-> {best_match['vendor']}")
                    
                    with self.db.transaction() as session:
                        # 重新查询获取 ORM 对象以避免 Session 冲突
                        target_trans = session.query(Transaction).get(best_match['id'])
                        if not target_trans:
                            return
                            
                        if target_trans.status == 'MATCHED':
                            self.db.log_system_event("MATCH_CONFLICT", "MatchEngine", f"Parallel shadow match conflict at {best_match['id']}")
                        
                        target_status = 'MATCHED'
                        if target_trans.group_id:
                            session.query(Transaction).filter(Transaction.group_id == target_trans.group_id).update({"status": target_status}, synchronize_session=False)
                        else:
                            target_trans.status = target_status
                                
                        session.query(PendingEntry).filter(PendingEntry.id == shadow_data['id']).update({"status": 'MATCHED'}, synchronize_session=False)
            except Exception as e:
                log.error(f"Worker 并行匹配异常: {e}")
            finally:
                self.task_queue.task_done()

    def run_matching(self):
        """
        [Optimization SQLAlchemy] 增强多模态逻辑成组匹配
        """
        log.info("执行多模态并行对账匹配任务...")
        self.db.update_heartbeat("MatchEngine-Master", "ACTIVE")
        
        try:
            # 1. 逻辑聚合
            with self.db.transaction() as session:
                # 查找 group_id 数量大于 1 的组
                subq = session.query(Transaction.group_id).group_by(Transaction.group_id).having(func.count(Transaction.id) > 1).subquery()
                session.query(Transaction).filter(
                    Transaction.group_id != None,
                    Transaction.status == 'PENDING',
                    Transaction.group_id.in_(subq)
                ).update({"status": "GROUPED"}, synchronize_session=False)

            if not hasattr(self, '_workers_started'):
                for _ in range(self.worker_count):
                    t = threading.Thread(target=self._match_worker, daemon=True)
                    t.start()
                self._workers_started = True

            # 2. 查找影子分录与潜在匹配项
            with self.db.transaction() as session:
                shadows_objs = session.query(PendingEntry).filter(PendingEntry.status == 'PENDING').all()
                
                for s in shadows_objs:
                    shadow_data = {"id": s.id, "amount": float(s.amount), "vendor_keyword": s.vendor_keyword, "created_at": s.created_at}
                    
                    # 查找潜在匹配项
                    # SQLAlchemy 中的时间差计算通常依赖具体方言，PG 使用 extract(epoch from ...)
                    candidates_objs = session.query(Transaction).filter(
                        Transaction.status.in_(['PENDING', 'GROUPED', 'MATCHED']),
                        Transaction.amount == s.amount,
                        func.abs(func.extract('epoch', shadow_data['created_at']) - func.extract('epoch', Transaction.created_at)) < 604800
                    ).all()
                    
                    candidates = [{"id": c.id, "vendor": c.vendor, "group_id": c.group_id, "status": c.status} for c in candidates_objs]
                    
                    self.task_queue.put((shadow_data, candidates))

            self.task_queue.join()
            
        except Exception as e:
            log.error(f"并行匹配异常: {e}")

    def _push_batch_reconcile_card(self, pairs):
        """推送批量对账消消乐卡片 (F3.4.1)"""
        try:
            log.info(f"正在异步记录批量消消乐建议 ({len(pairs)} 笔)")
            payload = {
                "type": "BATCH_MATCH",
                "data": {
                    "count": len(pairs),
                    "total_amount": float(sum(p['amount'] for p in pairs)),
                    "items": pairs[:5],
                    "action": "BATCH_CONFIRM"
                }
            }
            self.db.log_system_event("PUSH_CARD", "MatchEngine", json.dumps(payload, ensure_ascii=False))
        except Exception as e:
            log.error(f"发送批量卡片事件失败: {e}")

    def run_proactive_reminders(self):
        """
        [Optimization 5] 主动证据追索 (Evidence Hunter)
        """
        log.info("执行主动证据追索扫描 (Hunter Mode)...")
        try:
            with self.db.transaction() as session:
                # 查找 48 小时前创建且仍为 PENDING 的影子分录
                cutoff = func.now() - text("INTERVAL '2 days'")
                reminders_objs = session.query(PendingEntry).filter(
                    PendingEntry.status == 'PENDING',
                    PendingEntry.created_at < cutoff
                ).all()
                
                for r in reminders_objs:
                    log.warning(f"证据链断裂！向老板追索凭证: {r.vendor_keyword} (￥{r.amount})")
                    payload = {
                        "type": "EVIDENCE_REQUEST",
                        "data": {
                            "trans_id": r.id,
                            "vendor": r.vendor_keyword,
                            "amount": float(r.amount)
                        }
                    }
                    # 也可以在这里直接 session.add(SystemEvent(...))
                    self.db.log_system_event("EVIDENCE_REQUEST", "MatchEngine", json.dumps(payload, ensure_ascii=False))
        except Exception as e:
            log.error(f"证据追索任务异常: {e}")

    def main_loop(self):
        log.info("MatchEngine 守护进程模式启动 (并发模式)...")
        loop_interval = ConfigManager.get("intervals.match_engine_loop", 30)
        
        last_integrity_check = 0
        integrity_check_interval = 3600 
        
        last_reminder_check = 0
        reminder_interval = 14400 
        
        from infra.graceful_exit import should_exit
        while not should_exit():
            self.run_matching()
            
            now = time.time()
            if now - last_integrity_check > integrity_check_interval:
                log.info("启动周期性账本完整性校验...")
                success, msg = self.db.verify_chain_integrity()
                if success:
                    log.info(f"账本完整性校验通过: {msg}")
                    self.db.log_system_event("INTEGRITY_SUCCESS", "MatchEngine", msg)
                else:
                    log.critical(f"检测到账本异常风险: {msg}")
                    self.db.log_system_event("INTEGRITY_FAILURE", "MatchEngine", msg)
                last_integrity_check = now

            if now - last_reminder_check > reminder_interval:
                self.run_proactive_reminders()
                last_reminder_check = now
                
            time.sleep(loop_interval)

if __name__ == "__main__":
    MatchEngine().main_loop()
