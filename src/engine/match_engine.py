import time
import threading
import queue
import json
from difflib import SequenceMatcher
from decimal import Decimal
from collections import defaultdict

from core.db_helper import DBHelper
from core.db_models import Transaction, PendingEntry
from utils.decimal_utils import to_decimal
from utils.math_utils import find_subset_match
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
        if not s1 or not s2:
            return 0
        return SequenceMatcher(None, s1.lower(), s2.lower()).ratio()


class MatchEngine:
    def __init__(self):
        self.db = DBHelper()
        self.batch_size = 100
        self.time_window_days = 7
        self.fuzzy_threshold = 0.8
        self.worker_count = ConfigManager.get("match_engine.worker_count", 2)
        # N:M matching needs to process per-vendor, not per-item parallel
        self.lock = threading.Lock()

    def _group_by_vendor(self, shadows, transactions):
        """
        Groups pending items by vendor to prepare for N:M matching.
        Returns: { 'normalized_vendor': {'shadows': [], 'trans': []} }
        """
        groups = defaultdict(lambda: {"shadows": [], "trans": []})

        # We need a way to canonicalize vendor names.
        # For now, we use a simple normalization. In production, use Vector DB clustering.

        # 1. Assign Shadows (Receipts) to groups
        for s in shadows:
            # Simple normalization: First 2 chars + last 2 chars to handle minor typos?
            # Or just use the whole string lowercased.
            key = s.vendor_keyword.strip().lower() if s.vendor_keyword else "unknown"
            groups[key]["shadows"].append(s)

        # 2. Assign Transactions (Bank Flows) to groups
        # This is O(N*M) complexity if we do full fuzzy matching.
        # Optimization: Iterate transactions and find best fuzzy match in existing group keys
        group_keys = list(groups.keys())

        for t in transactions:
            t_vendor = t.vendor.strip().lower() if t.vendor else "unknown"

            # Try exact match first
            if t_vendor in groups:
                groups[t_vendor]["trans"].append(t)
                continue

            # Try fuzzy match
            best_key = None
            best_score = 0.0
            for k in group_keys:
                score = SequenceMatcher(None, t_vendor, k).ratio()
                if score > 0.8 and score > best_score:
                    best_score = score
                    best_key = k

            if best_key:
                groups[best_key]["trans"].append(t)
            else:
                # Create new group if distinct enough
                groups[t_vendor]["trans"].append(t)
                # Add to keys for subsequent matches
                group_keys.append(t_vendor)

        return groups

    def run_matching(self):
        log.info("执行 N:M 智能对账匹配任务...")
        self.db.update_heartbeat("MatchEngine-Master", "ACTIVE")

        try:
            with self.db.transaction() as session:
                shadows_objs = (
                    session.query(PendingEntry)
                    .filter(PendingEntry.status == "PENDING")
                    .all()
                )
                trans_objs = (
                    session.query(Transaction)
                    .filter(Transaction.status == "PENDING")
                    .all()
                )

                if not shadows_objs and not trans_objs:
                    return

                log.info(
                    f"Loaded {len(shadows_objs)} receipts and {len(trans_objs)} transactions for matching."
                )

                vendor_groups = self._group_by_vendor(shadows_objs, trans_objs)

                match_count = 0
                for v_key, group in vendor_groups.items():
                    s_list = group["shadows"]
                    t_list = group["trans"]

                    if not s_list or not t_list:
                        continue

                    s_amounts = [to_decimal(x.amount) for x in s_list]
                    t_amounts = [to_decimal(x.amount) for x in t_list]

                    result = find_subset_match(
                        s_amounts, t_amounts, tolerance=Decimal("0.10")
                    )

                    if result:
                        s_indices, t_indices = result

                        matched_shadows = [s_list[i] for i in s_indices]
                        matched_trans = [t_list[i] for i in t_indices]

                        match_group_id = f"MATCH_{int(time.time())}_{v_key[:4]}_{len(matched_shadows)}v{len(matched_trans)}"

                        total_amt = sum(s_amounts[i] for i in s_indices)
                        log.info(
                            f"✅ Found N:M Match for {v_key}: {len(matched_shadows)} Receipts vs {len(matched_trans)} Trans. Total: {total_amt}"
                        )

                        for s in matched_shadows:
                            s.status = "MATCHED"
                            # session.add(s) # Already in session

                        for t in matched_trans:
                            t.status = "MATCHED"
                            t.group_id = match_group_id
                            t.inference_log = t.inference_log or {}
                            if isinstance(t.inference_log, dict):
                                t.inference_log["match_info"] = {
                                    "type": "N:M_SUBSET_SUM",
                                    "group_id": match_group_id,
                                    "receipt_ids": [x.id for x in matched_shadows],
                                }
                                from sqlalchemy.orm.attributes import flag_modified

                                flag_modified(t, "inference_log")

                        match_count += 1

                        self._push_batch_reconcile_card(
                            matched_shadows, matched_trans, total_amt
                        )

            if match_count > 0:
                log.info(f"本轮对账完成，共生成 {match_count} 组匹配。")

        except Exception as e:
            log.error(f"N:M 匹配异常: {e}", exc_info=True)

    def _push_batch_reconcile_card(self, shadows, trans, total_amount):
        """推送对账成功卡片"""
        try:
            payload = {
                "type": "RECONCILIATION_SUCCESS",
                "data": {
                    "vendor": shadows[0].vendor_keyword,
                    "receipt_count": len(shadows),
                    "trans_count": len(trans),
                    "total_amount": float(total_amount),
                    "receipt_ids": [s.id for s in shadows],
                    "trans_ids": [t.id for t in trans],
                },
            }
            self.db.log_system_event(
                "PUSH_CARD", "MatchEngine", json.dumps(payload, ensure_ascii=False)
            )
        except Exception as e:
            log.error(f"发送对账卡片失败: {e}")

    def run_proactive_reminders(self):
        """
        [Optimization 5] 主动证据追索 (Evidence Hunter)
        """
        log.info("执行主动证据追索扫描 (Hunter Mode)...")
        try:
            with self.db.transaction() as session:
                # 查找 48 小时前创建且仍为 PENDING 的影子分录
                cutoff = func.now() - text("INTERVAL '2 days'")
                reminders_objs = (
                    session.query(PendingEntry)
                    .filter(
                        PendingEntry.status == "PENDING",
                        PendingEntry.created_at < cutoff,
                    )
                    .all()
                )

                for r in reminders_objs:
                    log.warning(
                        f"证据链断裂！向老板追索凭证: {r.vendor_keyword} (￥{r.amount})"
                    )
                    payload = {
                        "type": "EVIDENCE_REQUEST",
                        "data": {
                            "trans_id": r.id,
                            "vendor": r.vendor_keyword,
                            "amount": float(r.amount),
                        },
                    }
                    # 也可以在这里直接 session.add(SystemEvent(...))
                    self.db.log_system_event(
                        "EVIDENCE_REQUEST",
                        "MatchEngine",
                        json.dumps(payload, ensure_ascii=False),
                    )
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
