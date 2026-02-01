import hashlib
import json
import uuid
from core.db_base import DBBase
from infra.privacy_guard import PrivacyGuard
from infra.logger import get_logger

class DBTransactions(DBBase):
    """
    [Optimization Round 12] 事务性业务数据入库 (兼容 SQLite/PostgreSQL)
    """
    def _get_placeholder(self, index=0):
        return "%s" if self.db_type == "postgres" else "?"

    def add_transaction_with_chain(self, tags=None, **kwargs):
        if 'trace_id' not in kwargs or not kwargs['trace_id']:
            kwargs['trace_id'] = str(uuid.uuid4())
            
        guard = PrivacyGuard(role="DB_WRITER")
        if 'vendor' in kwargs and kwargs['vendor']:
            kwargs['vendor'] = guard.desensitize(kwargs['vendor'], context="GENERAL")
        
        try:
            with self.transaction() as conn:
                p = self._get_placeholder()
                if self.db_type == "postgres":
                    cur = conn.cursor()
                    # PG 语法
                    if kwargs.get("amount") and kwargs.get("vendor"):
                        cur.execute(f"SELECT id FROM transactions WHERE vendor = {p} AND amount = {p} AND created_at > CURRENT_TIMESTAMP - interval '5 minutes' LIMIT 1", (kwargs["vendor"], kwargs["amount"]))
                        if cur.fetchone(): return None
                    
                    cur.execute("SELECT chain_hash FROM transactions ORDER BY id DESC LIMIT 1")
                    last = cur.fetchone()
                    prev_hash = last[0] if last else "0" * 64
                    kwargs['prev_hash'] = prev_hash
                    kwargs['chain_hash'] = hashlib.sha256(json.dumps({"trace_id": kwargs['trace_id'], "amount": str(kwargs.get('amount')), "vendor": kwargs['vendor'], "prev_hash": prev_hash}, sort_keys=True).encode()).hexdigest()
                    
                    fields = ", ".join(kwargs.keys())
                    vals = tuple(kwargs.values())
                    cur.execute(f"INSERT INTO transactions ({fields}) VALUES ({', '.join([p]*len(kwargs))}) RETURNING id", vals)
                    trans_id = cur.fetchone()[0]
                else:
                    # SQLite 语法
                    if kwargs.get("amount") and kwargs.get("vendor"):
                        dup = conn.execute(f"SELECT id FROM transactions WHERE vendor = {p} AND amount = {p} AND created_at > datetime('now', '-5 minutes') LIMIT 1", (kwargs["vendor"], kwargs["amount"])).fetchone()
                        if dup: return None

                    last = conn.execute("SELECT chain_hash FROM transactions ORDER BY id DESC LIMIT 1").fetchone()
                    prev_hash = last['chain_hash'] if last else "0" * 64
                    kwargs['prev_hash'] = prev_hash
                    kwargs['chain_hash'] = hashlib.sha256(json.dumps({"trace_id": kwargs['trace_id'], "amount": str(kwargs.get('amount')), "vendor": kwargs['vendor'], "prev_hash": prev_hash}, sort_keys=True).encode()).hexdigest()
                    
                    fields = ", ".join(kwargs.keys())
                    vals = tuple(kwargs.values())
                    cursor = conn.execute(f"INSERT INTO transactions ({fields}) VALUES ({', '.join([p]*len(kwargs))})", vals)
                    trans_id = cursor.lastrowid

                if trans_id and tags:
                    tag_sql = f"INSERT INTO transaction_tags (transaction_id, tag_key, tag_value) VALUES ({p}, {p}, {p})"
                    if self.db_type == "postgres":
                        for tag in tags: cur.execute(tag_sql, (trans_id, tag['key'], tag['value']))
                    else:
                        for tag in tags: conn.execute(tag_sql, (trans_id, tag['key'], tag['value']))
                return trans_id
        except Exception as e:
            get_logger("DB-Chain").error(f"链式入库失败: {e}")
            return None

    def add_transaction(self, **kwargs):
        if 'trace_id' not in kwargs or not kwargs['trace_id']:
            kwargs['trace_id'] = str(uuid.uuid4())
        # ... 类似逻辑兼容处理 ...
        return self.add_transaction_with_chain(None, **kwargs) # 简化示例

    def add_pending_entries_batch(self, entries):
        try:
            with self.transaction() as conn:
                p = self._get_placeholder()
                sql = f"INSERT INTO pending_entries (amount, vendor_keyword) VALUES ({p}, {p})"
                params = [(e['amount'], e['vendor_keyword']) for e in entries]
                if self.db_type == "postgres":
                    conn.cursor().executemany(sql, params)
                else:
                    conn.executemany(sql, params)
                return True
        except Exception as e:
            get_logger("DB-Batch").error(f"批量插入失败: {e}")
            return False

    def add_pending_entry(self, **kwargs):
        try:
            with self.transaction() as conn:
                p = self._get_placeholder()
                fields = ", ".join(kwargs.keys())
                vals = tuple(kwargs.values())
                sql = f"INSERT INTO pending_entries ({fields}) VALUES ({', '.join([p]*len(kwargs))})"
                if self.db_type == "postgres":
                    cur = conn.cursor()
                    cur.execute(sql + " RETURNING id", vals)
                    return cur.fetchone()[0]
                else:
                    cursor = conn.execute(sql, vals)
                    return cursor.lastrowid
        except Exception as e:
            get_logger("DB").error(f"影子分录入库失败: {e}")
            return None

    def update_trial_balance(self, category, amount, direction=None):
        try:
            if direction is None:
                direction = "DEBIT" if (category.startswith("1") or category.startswith("5") or "费用" in category) else "CREDIT"
            with self.transaction() as conn:
                p = self._get_placeholder()
                field = "debit_total" if direction == "DEBIT" else "credit_total"
                if self.db_type == "postgres":
                    sql = f"INSERT INTO trial_balance (account_code, {field}, updated_at) VALUES ({p}, {p}, CURRENT_TIMESTAMP) ON CONFLICT(account_code) DO UPDATE SET {field} = trial_balance.{field} + EXCLUDED.{field}, updated_at = CURRENT_TIMESTAMP"
                    conn.cursor().execute(sql, (category, amount))
                else:
                    sql = f"INSERT INTO trial_balance (account_code, {field}, updated_at) VALUES ({p}, {p}, CURRENT_TIMESTAMP) ON CONFLICT(account_code) DO UPDATE SET {field} = {field} + excluded.{field}, updated_at = CURRENT_TIMESTAMP"
                    conn.execute(sql, (category, amount))
                return True
        except Exception as e:
            get_logger("DB-Balance").error(f"更新试算平衡失败: {e}")
            return False

    def mark_transaction_reverted(self, trans_id, reason="Manual Revert"):
        try:
            with self.transaction() as conn:
                p = self._get_placeholder()
                if self.db_type == "postgres":
                    cur = conn.cursor()
                    cur.execute(f"SELECT vendor, status, category, amount FROM transactions WHERE id = {p}", (trans_id,))
                    row = cur.fetchone()
                    if not row: return False
                    vendor, old_status, category, amount = row
                    cur.execute(f"UPDATE transactions SET logical_revert = 1, status = 'REVERTED' WHERE id = {p}", (trans_id,))
                    if category and amount: self.update_trial_balance(category, -amount)
                    if old_status in ('AUDITED', 'POSTED', 'COMPLETED'):
                        cur.execute(f"UPDATE knowledge_base SET consecutive_success = GREATEST(0, consecutive_success - 1), hit_count = GREATEST(0, hit_count - 1), quality_score = GREATEST(0.5, quality_score - 0.05) WHERE entity_name = {p}", (vendor,))
                else:
                    row = conn.execute(f"SELECT vendor, status, category, amount FROM transactions WHERE id = {p}", (trans_id,)).fetchone()
                    if not row: return False
                    vendor, old_status, category, amount = row['vendor'], row['status'], row['category'], row['amount']
                    conn.execute(f"UPDATE transactions SET logical_revert = 1, status = 'REVERTED' WHERE id = {p}", (trans_id,))
                    if category and amount: self.update_trial_balance(category, -amount)
                    if old_status in ('AUDITED', 'POSTED', 'COMPLETED'):
                        conn.execute(f"UPDATE knowledge_base SET consecutive_success = MAX(0, consecutive_success - 1), hit_count = MAX(0, hit_count - 1), quality_score = MAX(0.5, quality_score - 0.05) WHERE entity_name = {p}", (vendor,))
                return True
        except Exception as e:
            get_logger("DB-Revert").error(f"逻辑回撤失败: {e}")
            return False
