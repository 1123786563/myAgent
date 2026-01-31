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
                for f in potential_matches:
                    is_match = False
                    if not shadow['vendor_keyword']:
                        is_match = True
                    else:
                        v_key = shadow['vendor_keyword'].lower()
                        v_target = (f['vendor'] or "").lower()
                        if v_key in v_target:
                            is_match = True
                        elif MatchStrategy.get_fuzzy_ratio(v_key, v_target) > self.fuzzy_threshold:
                            is_match = True
                            
                    if is_match:
                        # 注意：更新数据库仍需在主线程或加锁事务中完成，此处仅标记结果
                        shadow['match_result'] = f['id']
                        break
            except Exception as e:
                log.error(f"Worker 匹配异常: {e}")
            finally:
                self.task_queue.task_done()

    def run_matching(self):
        """
        并发化的匹配主逻辑：解耦策略与流程，利用多线程加速计算
        """
        log.info("执行并发对账匹配任务...")
        self.db.update_heartbeat("MatchEngine-Master", "ACTIVE")
        
        try:
            orphans = self.db.fix_orphaned_transactions()
            if orphans > 0: log.info(f"清理了 {orphans} 条残留中间态单据")

            # 启动工作者线程
            workers = []
            for _ in range(self.worker_count):
                t = threading.Thread(target=self._match_worker, daemon=True)
                t.start()
                workers.append(t)

            with self.db.transaction("EXCLUSIVE") as conn:
                cursor = conn.cursor()
                cursor.execute(f"SELECT id, amount, vendor_keyword FROM pending_entries WHERE status = 'PENDING' LIMIT {self.batch_size}")
                shadows = [dict(row) for row in cursor.fetchall()]

                # 预读所有可能的匹配项
                for s in shadows:
                    cursor.execute("""
                        SELECT id, amount, vendor FROM transactions 
                        WHERE status = 'PENDING' 
                        AND amount BETWEEN ? AND ?
                        AND (strftime('%s', 'now') - strftime('%s', created_at)) < ?
                    """, (s['amount']-0.05, s['amount']+0.05, self.time_window_days * 86400))
                    potential_matches = [dict(row) for row in cursor.fetchall()]
                    
                    self.task_queue.put((s, potential_matches))

                # 等待所有计算完成
                self.task_queue.join()

                # 批量提交结果与 IM 联动 (F3.4.1)
                matched_pairs = []
                for s in shadows:
                    if 'match_result' in s:
                        cursor.execute("UPDATE transactions SET status = 'MATCHED' WHERE id = ?", (s['match_result'],))
                        cursor.execute("UPDATE pending_entries SET status = 'MATCHED' WHERE id = ?", (s['id'],))
                        log.info(f"并发匹配成功: {s['vendor_keyword']} | ID:{s['match_result']}")
                        matched_pairs.append({
                            "shadow_id": s['id'],
                            "trans_id": s['match_result'],
                            "vendor": s['vendor_keyword'],
                            "amount": s['amount']
                        })
                
                # 优化点：推送批量消消乐卡片
                if matched_pairs:
                    self._push_batch_reconcile_card(matched_pairs)

            # 停止工作者
            for _ in range(self.worker_count):
                self.task_queue.put(None)
            for t in workers:
                t.join()

        except Exception as e:
            log.error(f"并发对账异常: {e}")

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

    def main_loop(self):
        log.info("MatchEngine 守护进程模式启动 (并发模式)...")
        loop_interval = ConfigManager.get("intervals.match_engine_loop", 30)
        while True:
            self.run_matching()
            time.sleep(loop_interval)

if __name__ == "__main__":
    MatchEngine().main_loop()
