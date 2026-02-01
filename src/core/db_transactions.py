import hashlib
import json
import uuid
import psycopg2.extras
from core.db_base import DBBase
from infra.privacy_guard import PrivacyGuard
from infra.logger import get_logger

class DBTransactions(DBBase):
    """
    [Optimization Round 12 - PG Only] 事务性业务数据入库 (PostgreSQL 专版)
    """
    def _get_placeholder(self, index=0):
        return "%s"

    def add_transaction_with_chain(self, tags=None, **kwargs):
        if 'trace_id' not in kwargs or not kwargs['trace_id']:
            kwargs['trace_id'] = str(uuid.uuid4())
            
        guard = PrivacyGuard(role="DB_WRITER")
        if 'vendor' in kwargs and kwargs['vendor']:
            kwargs['vendor'] = guard.desensitize(kwargs['vendor'], context="GENERAL")
        
        try:
            with self.transaction() as conn:
                cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
                
                # 防重逻辑
                if kwargs.get("amount") and kwargs.get("vendor"):
                    cur.execute("SELECT id FROM transactions WHERE vendor = %s AND amount = %s AND created_at > CURRENT_TIMESTAMP - interval '5 minutes' LIMIT 1", (kwargs["vendor"], kwargs["amount"]))
                    if cur.fetchone(): return None
                
                # 链式校验
                cur.execute("SELECT chain_hash FROM transactions ORDER BY id DESC LIMIT 1")
                last = cur.fetchone()
                prev_hash = last['chain_hash'] if last else "0" * 64
                kwargs['prev_hash'] = prev_hash
                kwargs['chain_hash'] = hashlib.sha256(json.dumps({"trace_id": kwargs['trace_id'], "amount": str(kwargs.get('amount')), "vendor": kwargs['vendor'], "prev_hash": prev_hash}, sort_keys=True).encode()).hexdigest()
                
                # 动态插入
                fields = ", ".join(kwargs.keys())
                vals = tuple(kwargs.values())
                cur.execute(f"INSERT INTO transactions ({fields}) VALUES ({', '.join(['%s']*len(kwargs))}) RETURNING id", vals)
                trans_id = cur.fetchone()['id']

                if trans_id and tags:
                    tag_sql = "INSERT INTO transaction_tags (transaction_id, tag_key, tag_value) VALUES (%s, %s, %s)"
                    for tag in tags: cur.execute(tag_sql, (trans_id, tag['key'], tag['value']))
                
                return trans_id
        except Exception as e:
            get_logger("DB-Chain").error(f"链式入库失败: {e}")
            return None

    def add_transaction(self, **kwargs):
        return self.add_transaction_with_chain(None, **kwargs)

    def add_pending_entries_batch(self, entries):
        try:
            with self.transaction() as conn:
                sql = "INSERT INTO pending_entries (amount, vendor_keyword) VALUES (%s, %s)"
                params = [(e['amount'], e['vendor_keyword']) for e in entries]
                with conn.cursor() as cur:
                    cur.executemany(sql, params)
                return True
        except Exception as e:
            get_logger("DB-Batch").error(f"批量插入失败: {e}")
            return False

    def add_pending_entry(self, **kwargs):
        try:
            with self.transaction() as conn:
                fields = ", ".join(kwargs.keys())
                vals = tuple(kwargs.values())
                sql = f"INSERT INTO pending_entries ({fields}) VALUES ({', '.join(['%s']*len(kwargs))}) RETURNING id"
                with conn.cursor() as cur:
                    cur.execute(sql, vals)
                    return cur.fetchone()[0]
        except Exception as e:
            get_logger("DB").error(f"影子分录入库失败: {e}")
            return None

    def update_trial_balance(self, category, amount, direction=None):
        try:
            if direction is None:
                direction = "DEBIT" if (category.startswith("1") or category.startswith("5") or "费用" in category) else "CREDIT"
            with self.transaction() as conn:
                field = "debit_total" if direction == "DEBIT" else "credit_total"
                sql = f"INSERT INTO trial_balance (account_code, {field}, updated_at) VALUES (%s, %s, CURRENT_TIMESTAMP) ON CONFLICT(account_code) DO UPDATE SET {field} = trial_balance.{field} + EXCLUDED.{field}, updated_at = CURRENT_TIMESTAMP"
                with conn.cursor() as cur:
                    cur.execute(sql, (category, amount))
                return True
        except Exception as e:
            get_logger("DB-Balance").error(f"更新试算平衡失败: {e}")
            return False

    def mark_transaction_reverted(self, trans_id, reason="Manual Revert"):
        try:
            with self.transaction() as conn:
                cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
                cur.execute("SELECT vendor, status, category, amount FROM transactions WHERE id = %s", (trans_id,))
                row = cur.fetchone()
                if not row: return False
                vendor, old_status, category, amount = row['vendor'], row['status'], row['category'], row['amount']
                
                cur.execute("UPDATE transactions SET logical_revert = 1, status = 'REVERTED' WHERE id = %s", (trans_id,))
                if category and amount: self.update_trial_balance(category, -amount)
                
                if old_status in ('AUDITED', 'POSTED', 'COMPLETED'):
                    cur.execute("UPDATE knowledge_base SET consecutive_success = GREATEST(0, consecutive_success - 1), hit_count = GREATEST(0, hit_count - 1), quality_score = GREATEST(0.5, quality_score - 0.05) WHERE entity_name = %s", (vendor,))
                return True
        except Exception as e:
            get_logger("DB-Revert").error(f"逻辑回撤失败: {e}")
            return False
