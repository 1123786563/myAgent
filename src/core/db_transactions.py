import hashlib
import json
import uuid
import sqlite3
from core.db_base import DBBase
from infra.privacy_guard import PrivacyGuard
from infra.logger import get_logger

class DBTransactions(DBBase):
    """
    [Optimization Round 12] 事务性业务数据入库
    """
    def add_transaction_with_chain(self, tags=None, **kwargs):
        if 'trace_id' not in kwargs or not kwargs['trace_id']:
            kwargs['trace_id'] = str(uuid.uuid4())
            
        guard = PrivacyGuard(role="DB_WRITER")
        if 'vendor' in kwargs and kwargs['vendor']:
            kwargs['vendor'] = guard.desensitize(kwargs['vendor'], context="GENERAL")
        
        try:
            with self.transaction("IMMEDIATE") as conn:
                if kwargs.get("amount") and kwargs.get("vendor"):
                    dup = conn.execute("SELECT id FROM transactions WHERE vendor = ? AND amount = ? AND created_at > datetime('now', '-5 minutes') LIMIT 1", (kwargs["vendor"], kwargs["amount"])).fetchone()
                    if dup: return None

                last_row = conn.execute("SELECT chain_hash FROM transactions ORDER BY id DESC LIMIT 1").fetchone()
                prev_hash = last_row['chain_hash'] if last_row else "0" * 64
                kwargs['prev_hash'] = prev_hash
                
                data_to_hash = {"trace_id": kwargs.get('trace_id'), "amount": str(kwargs.get('amount')), "vendor": kwargs.get('vendor'), "prev_hash": prev_hash}
                kwargs['chain_hash'] = hashlib.sha256(json.dumps(data_to_hash, sort_keys=True).encode()).hexdigest()
                
                fields = ", ".join(kwargs.keys())
                placeholders = ", ".join(["?"] * len(kwargs))
                values = tuple(kwargs.values())
                sql = f"INSERT OR IGNORE INTO transactions ({fields}) VALUES ({placeholders})"
                cursor = conn.execute(sql, values)
                trans_id = cursor.lastrowid

                if trans_id and tags:
                    tag_sql = "INSERT INTO transaction_tags (transaction_id, tag_key, tag_value) VALUES (?, ?, ?)"
                    for tag in tags:
                        conn.execute(tag_sql, (trans_id, tag['key'], tag['value']))
                return trans_id
        except Exception as e:
            get_logger("DB-Chain").error(f"链式入库失败: {e}")
            return None

    def add_transaction(self, **kwargs):
        if 'trace_id' not in kwargs or not kwargs['trace_id']:
            kwargs['trace_id'] = str(uuid.uuid4())

        guard = PrivacyGuard(role="DB_WRITER")
        if 'vendor' in kwargs and kwargs['vendor']:
            kwargs['vendor'] = guard.desensitize(kwargs['vendor'], context="GENERAL")
            
        if 'inference_log' in kwargs:
            log_data = kwargs['inference_log']
            if isinstance(log_data, dict):
                 if 'cot_trace' in log_data and isinstance(log_data['cot_trace'], list):
                     for step in log_data['cot_trace']:
                         if 'details' in step and isinstance(step['details'], str):
                             step['details'] = guard.desensitize(step['details'], context="GENERAL")
                 kwargs['inference_log'] = json.dumps(log_data, ensure_ascii=False)
            elif isinstance(log_data, str):
                kwargs['inference_log'] = guard.desensitize(log_data, context="GENERAL")

        fields = ", ".join(kwargs.keys())
        placeholders = ", ".join(["?"] * len(kwargs))
        values = tuple(kwargs.values())
        
        sql = f"INSERT OR IGNORE INTO transactions ({fields}) VALUES ({placeholders})"
        try:
            with self.transaction("IMMEDIATE") as conn:
                cursor = conn.cursor()
                cursor.execute(sql, values)
                if cursor.rowcount == 0 and 'trace_id' in kwargs:
                    check_sql = "SELECT id FROM transactions WHERE trace_id = ?"
                    res = conn.execute(check_sql, (kwargs['trace_id'],)).fetchone()
                    if res:
                        return res['id']
                return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None

    def add_pending_entries_batch(self, entries):
        try:
            with self.transaction("IMMEDIATE") as conn:
                sql = "INSERT INTO pending_entries (amount, vendor_keyword) VALUES (?, ?)"
                params = [(e['amount'], e['vendor_keyword']) for e in entries]
                conn.executemany(sql, params)
                return True
        except Exception as e:
            get_logger("DB-Batch").error(f"批量插入失败: {e}")
            return False

    def add_pending_entry(self, **kwargs):
        fields = ", ".join(kwargs.keys())
        placeholders = ", ".join(["?"] * len(kwargs))
        values = tuple(kwargs.values())
        sql = f"INSERT INTO pending_entries ({fields}) VALUES ({placeholders})"
        try:
            with self.transaction("IMMEDIATE") as conn:
                cursor = conn.execute(sql, values)
                return cursor.lastrowid
        except Exception as e:
            get_logger("DB").error(f"影子分录入库失败: {e}")
            return None

    def update_trial_balance(self, category, amount, direction=None):
        try:
            if direction is None:
                if category.startswith("1") or category.startswith("5") or "费用" in category:
                    direction = "DEBIT"
                else:
                    direction = "CREDIT"

            with self.transaction("IMMEDIATE") as conn:
                field = "debit_total" if direction == "DEBIT" else "credit_total"
                sql = f"""
                    INSERT INTO trial_balance (account_code, {field}, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(account_code) DO UPDATE SET
                        {field} = {field} + excluded.{field},
                        updated_at = CURRENT_TIMESTAMP
                """
                conn.execute(sql, (category, amount))
                return True
        except Exception as e:
            get_logger("DB-Balance").error(f"更新试算平衡失败: {e}")
            return False

    def mark_transaction_reverted(self, trans_id, reason="Manual Revert"):
        """[Iteration 7/9] 逻辑回撤：联动扣减信任分 + 自动冲销试算平衡"""
        try:
            with self.transaction("IMMEDIATE") as conn:
                # 1. 获取供应商与科目金额信息
                row = conn.execute("SELECT vendor, status, category, amount FROM transactions WHERE id = ?", (trans_id,)).fetchone()
                if not row: return False
                
                vendor = row['vendor']
                old_status = row['status']
                category = row['category']
                amount = row['amount']

                # 2. 标记回撤
                conn.execute("UPDATE transactions SET logical_revert = 1, status = 'REVERTED' WHERE id = ?", (trans_id,))
                
                # 3. [Iteration 9] 自动冲销试算平衡
                if category and amount:
                    # 反向操作：传入负金额
                    self.update_trial_balance(category, -amount)

                # 4. 联动扣减信任分 (如果之前是 APPROVED)
                if old_status in ('AUDITED', 'POSTED', 'COMPLETED'):
                    conn.execute("""
                        UPDATE knowledge_base 
                        SET consecutive_success = MAX(0, consecutive_success - 1),
                            hit_count = MAX(0, hit_count - 1),
                            quality_score = MAX(0.5, quality_score - 0.05)
                        WHERE entity_name = ?
                    """, (vendor,))
                
                get_logger("DB-Revert").warning(f"ID {trans_id} 已回撤并完成账务冲销，原因: {reason}")
                return True
        except Exception as e:
            get_logger("DB-Revert").error(f"逻辑回撤失败: {e}")
            return False
