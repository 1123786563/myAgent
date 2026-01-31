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
                    
                    # [Optimization 4] 语义消消乐：金额一致时增强户名语义对齐
                    v_key = (shadow['vendor_keyword'] or "").lower()
                    v_target = (f['vendor'] or "").lower()
                    
                    if not v_key:
                        is_match = True
                    elif v_key in v_target or v_target in v_key:
                        is_match = True
                    else:
                        # [Optimization 4] 增强型多因子匹配 (Multi-Factor Matching)
                        # 引入模糊比例计算 + 时间衰减因子
                        ratio = MatchStrategy.get_fuzzy_ratio(v_key, v_target)
                        
                        # 计算时间接近度 (天数差)
                        try:
                            t_shadow = time.mktime(time.strptime(shadow['created_at'], "%Y-%m-%d %H:%M:%S"))
                            t_target = time.mktime(time.strptime(f['created_at'], "%Y-%m-%d %H:%M:%S"))
                            days_diff = abs(t_shadow - t_target) / 86400.0
                            date_score = max(0, 1.0 - (days_diff / 7.0)) # 7天内线性衰减
                        except:
                            date_score = 0.5

                        # 综合评分：语义(70%) + 时间(30%)
                        final_score = (ratio * 0.7) + (date_score * 0.3)
                        
                        if final_score > self.fuzzy_threshold:
                            is_match = True
                            log.info(f"多因子匹配成功: {v_key} <-> {v_target} (Score: {final_score:.2f} | DateDiff: {days_diff:.1f}d)")
                            
                    if is_match:
                        shadow['match_result'] = f['id']
                        break
            except Exception as e:
                log.error(f"Worker 匹配异常: {e}")
            finally:
                self.task_queue.task_done()

    def run_matching(self):
        """
        [Optimization 1] 增强多模态逻辑成组匹配 (F3.1.3)
        实现“消消乐”算法：Bank_Flow (影子) + OCR_Receipt (实体) = Audited_Transaction
        同时聚合具有相同 group_id 的多模态实物单据。
        """
        log.info("执行多模态增强对账匹配任务...")
        self.db.update_heartbeat("MatchEngine-Master", "ACTIVE")
        
        try:
            # 1. 逻辑聚合：相同 group_id 的单据自动提升优先级并标记 (Optimization 1)
            with self.db.transaction("IMMEDIATE") as conn:
                conn.execute("""
                    UPDATE transactions 
                    SET status = 'GROUPED' 
                    WHERE group_id IS NOT NULL AND status = 'PENDING'
                    AND group_id IN (SELECT group_id FROM transactions GROUP BY group_id HAVING COUNT(*) > 1)
                """)
                
                # [Optimization 4] 生成多模态资产画像事件
                sql_grouped = "SELECT group_id, COUNT(*) as cnt FROM transactions WHERE status = 'GROUPED' GROUP BY group_id"
                groups = conn.execute(sql_grouped).fetchall()
                for g in groups:
                    self.db.log_system_event("ASSET_BUNDLE_DETECTED", "MatchEngine", f"Detected Asset Bundle {g['group_id']} with {g['cnt']} images.")

            # 2. 查找所有 PENDING 状态的影子分录
            with self.db.transaction("DEFERRED") as conn:
                cursor = conn.execute("SELECT id, amount, vendor_keyword, created_at FROM pending_entries WHERE status = 'PENDING'")
                shadows = [dict(row) for row in cursor.fetchall()]

            for s in shadows:
                # 3. 在实体单据中搜索匹配项
                # 逻辑：金额一致 + 时间窗口（7天内）+ 供应商语义匹配
                with self.db.transaction("IMMEDIATE") as conn:
                    cursor = conn.execute("""
                        SELECT id, vendor, group_id FROM transactions 
                        WHERE status IN ('PENDING', 'GROUPED') 
                        AND amount = ? 
                        AND ABS(strftime('%s', ?) - strftime('%s', created_at)) < 604800
                    """, (s['amount'], s['created_at']))
                    matches = [dict(row) for row in cursor.fetchall()]
                    
                    for m in matches:
                        v_key = s['vendor_keyword'].lower()
                        v_target = m['vendor'].lower()
                        # 简单的语义匹配
                        if v_key in v_target or v_target in v_key:
                            log.info(f"消消乐匹配成功: {s['vendor_keyword']} <-> {m['vendor']} (ID: {m['id']})")
                            
                            # 如果匹配项是成组照片的一部分，执行整体聚合逻辑
                            if m.get('group_id'):
                                log.info(f"匹配项属于逻辑组 {m['group_id']}，执行整组消消乐...")
                                conn.execute("UPDATE transactions SET status = 'MATCHED' WHERE group_id = ?", (m['group_id'],))
                            else:
                                conn.execute("UPDATE transactions SET status = 'MATCHED' WHERE id = ?", (m['id'],))
                                
                            conn.execute("UPDATE pending_entries SET status = 'MATCHED' WHERE id = ?", (s['id'],))
                            break
        except Exception as e:
            log.error(f"影子匹配异常: {e}")

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
        
        while True:
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
