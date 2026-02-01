import time
import threading
import queue
from difflib import SequenceMatcher
from db_helper import DBHelper
from logger import get_logger
from config_manager import ConfigManager

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
            
            shadow, potential_matches = task
            try:
                best_match = None
                max_score = 0.0
                
                for c in potential_matches:
                    # 计算匹配分 (使用 MatchStrategy)
                    score = MatchStrategy.get_fuzzy_ratio(shadow['vendor_keyword'], c['vendor'])
                    
                    # [Round 13/18] 状态权重：优先匹配未对账的
                    if c['status'] != 'MATCHED':
                        score += 0.1
                        
                    if score > self.fuzzy_threshold and score > max_score:
                        max_score = score
                        best_match = c
                
                if best_match:
                    log.info(f"消消乐并行匹配成功 (Score: {max_score:.2f}): {shadow['vendor_keyword']} <-> {best_match['vendor']}")
                    
                    # 异步任务中的写回逻辑
                    with self.db.transaction("IMMEDIATE") as conn:
                        # 再次检查冲突
                        if best_match['status'] == 'MATCHED':
                            self.db.log_system_event("MATCH_CONFLICT", "MatchEngine", f"Parallel shadow match conflict at {best_match['id']}")
                        
                        target_status = 'MATCHED'
                        if best_match.get('group_id'):
                            conn.execute("UPDATE transactions SET status = ? WHERE group_id = ?", (target_status, best_match['group_id']))
                        else:
                            conn.execute("UPDATE transactions SET status = ? WHERE id = ?", (target_status, best_match['id']))
                                
                        conn.execute("UPDATE pending_entries SET status = 'MATCHED' WHERE id = ?", (shadow['id'],))
            except Exception as e:
                log.error(f"Worker 并行匹配异常: {e}")
            finally:
                self.task_queue.task_done()

    def run_matching(self):
        """
        [Optimization 1] 增强多模态逻辑成组匹配 (F3.1.3)
        [Optimization Round 13] 增加批量匹配优化与冲突检测
        [Optimization Round 18] 并行化匹配引擎，使用 Worker 线程池
        """
        log.info("执行多模态并行对账匹配任务...")
        self.db.update_heartbeat("MatchEngine-Master", "ACTIVE")
        
        try:
            # 1. 逻辑聚合 (保持原有逻辑)
            with self.db.transaction("IMMEDIATE") as conn:
                conn.execute("""
                    UPDATE transactions 
                    SET status = 'GROUPED' 
                    WHERE group_id IS NOT NULL AND status = 'PENDING'
                    AND group_id IN (SELECT group_id FROM transactions GROUP BY group_id HAVING COUNT(*) > 1)
                """)

            # 启动并行的 Worker (如果尚未启动)
            if not hasattr(self, '_workers_started'):
                for _ in range(self.worker_count):
                    t = threading.Thread(target=self._match_worker, daemon=True)
                    t.start()
                self._workers_started = True

            # 2. 查找影子分录与潜在匹配项
            with self.db.transaction("DEFERRED") as conn:
                cursor = conn.execute("SELECT id, amount, vendor_keyword, created_at FROM pending_entries WHERE status = 'PENDING'")
                shadows = [dict(row) for row in cursor.fetchall()]
                
                # 为每一笔流水预加载潜在匹配项以减少锁竞争
                for s in shadows:
                    cursor = conn.execute("""
                        SELECT id, vendor, group_id, status FROM transactions 
                        WHERE status IN ('PENDING', 'GROUPED', 'MATCHED') 
                        AND amount = ? 
                        AND ABS(strftime('%s', ?) - strftime('%s', created_at)) < 604800
                    """, (s['amount'], s['created_at']))
                    candidates = [dict(row) for row in cursor.fetchall()]
                    
                    # 将任务投入队列
                    self.task_queue.put((s, candidates))

            # 等待本批次处理完成
            self.task_queue.join()
            
        except Exception as e:
            log.error(f"并行匹配异常: {e}")

    def _push_batch_reconcile_card(self, pairs):
        """推送批量对账消消乐卡片 (F3.4.1)"""
        try:
            from interaction_hub import InteractionHub
            hub = InteractionHub()
            log.info(f"正在通过 InteractionHub 推送批量消消乐建议 ({len(pairs)} 笔)")
            hub.push_card("BATCH_MATCH", {
                "count": len(pairs),
                "total_amount": sum(p['amount'] for p in pairs),
                "items": pairs[:5], # 仅展示前5笔作为摘要
                "action": "BATCH_CONFIRM"
            })
        except Exception as e:
            log.error(f"推送批量卡片失败: {e}")

    def run_proactive_reminders(self):
        """
        [Optimization 5] 主动证据追索 (Evidence Hunter)
        逻辑：网银流水产生 > 48h 且未对冲，推送催办卡片 (F4.5)
        """
        log.info("执行主动证据追索扫描 (Hunter Mode)...")
        try:
            with self.db.transaction("DEFERRED") as conn:
                # 查找 48 小时前创建且仍为 PENDING 的影子分录 (Shadow Entries)
                sql = """
                    SELECT id, amount, vendor_keyword, created_at 
                    FROM pending_entries 
                    WHERE status = 'PENDING' 
                    AND datetime(created_at) < datetime('now', '-2 days')
                """
                reminders = [dict(row) for row in conn.execute(sql).fetchall()]
                
            from interaction_hub import InteractionHub
            hub = InteractionHub()
            for r in reminders:
                log.warning(f"证据链断裂！向老板追索凭证: {r['vendor_keyword']} (￥{r['amount']})")
                hub.push_evidence_request(r['id'], r['vendor_keyword'], r['amount'])
        except Exception as e:
            log.error(f"证据追索任务异常: {e}")

    def main_loop(self):
        log.info("MatchEngine 守护进程模式启动 (并发模式)...")
        loop_interval = ConfigManager.get("intervals.match_engine_loop", 30)
        
        # [Optimization 2] 初始化完整性校验计数器
        last_integrity_check = 0
        integrity_check_interval = 3600 # 每小时一次
        
        # [Optimization 3] 提醒任务计数器
        last_reminder_check = 0
        reminder_interval = 14400 # 每 4 小时一次
        
        from graceful_exit import should_exit
        while not should_exit():
            self.run_matching()
            
            now = time.time()
            # 1. 周期性验证区块链证据链完整性 (Suggestion 5)
            if now - last_integrity_check > integrity_check_interval:
                # ... (保持原有校验逻辑)
                log.info("启动周期性账本完整性校验...")
                success, msg = self.db.verify_chain_integrity()
                if success:
                    log.info(f"账本完整性校验通过: {msg}")
                    self.db.log_system_event("INTEGRITY_SUCCESS", "MatchEngine", msg)
                else:
                    log.critical(f"检测到账本异常风险: {msg}")
                    self.db.log_system_event("INTEGRITY_FAILURE", "MatchEngine", msg)
                last_integrity_check = now

            # 2. [Optimization 3] 执行主动证据追索
            if now - last_reminder_check > reminder_interval:
                self.run_proactive_reminders()
                last_reminder_check = now
                
            time.sleep(loop_interval)

if __name__ == "__main__":
    MatchEngine().main_loop()
