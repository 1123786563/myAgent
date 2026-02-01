import hashlib
import json
import uuid
from core.db_base import DBBase
from core.db_models import Transaction, TransactionTag, PendingEntry, TrialBalance, KnowledgeBase
from infra.privacy_guard import PrivacyGuard
from infra.logger import get_logger
from sqlalchemy import func, text

class DBTransactions(DBBase):
    """
    [Optimization Round 12 - SQLAlchemy] 事务性业务数据入库
    """
    def add_transaction_with_chain(self, tags=None, **kwargs):
        if 'trace_id' not in kwargs or not kwargs['trace_id']:
            kwargs['trace_id'] = str(uuid.uuid4())
            
        guard = PrivacyGuard(role="DB_WRITER")
        if 'vendor' in kwargs and kwargs['vendor']:
            kwargs['vendor'] = guard.desensitize(kwargs['vendor'], context="GENERAL")
        
        try:
            with self.transaction() as session:
                # 防重逻辑
                if kwargs.get("amount") and kwargs.get("vendor"):
                    exists = session.query(Transaction.id).filter(
                        Transaction.vendor == kwargs["vendor"],
                        Transaction.amount == kwargs["amount"],
                        Transaction.created_at > func.now() - text("interval '5 minutes'")
                    ).first()
                    if exists: return None
                
                # 链式校验
                last = session.query(Transaction.chain_hash).order_by(Transaction.id.desc()).first()
                prev_hash = last.chain_hash if last else "0" * 64
                kwargs['prev_hash'] = prev_hash
                kwargs['chain_hash'] = hashlib.sha256(json.dumps({
                    "trace_id": kwargs['trace_id'], 
                    "amount": str(kwargs.get('amount')), 
                    "vendor": kwargs['vendor'], 
                    "prev_hash": prev_hash
                }, sort_keys=True).encode()).hexdigest()
                
                # 构造并保存 Transaction 对象
                trans = Transaction(**kwargs)
                session.add(trans)
                session.flush() # 获取 ID

                if trans.id and tags:
                    for tag in tags:
                        t_tag = TransactionTag(
                            transaction_id=trans.id,
                            tag_key=tag['key'],
                            tag_value=tag['value']
                        )
                        session.add(t_tag)
                
                return trans.id
        except Exception as e:
            get_logger("DB-Chain").error(f"链式入库失败: {e}")
            return None

    def add_transaction(self, **kwargs):
        return self.add_transaction_with_chain(None, **kwargs)

    def add_pending_entries_batch(self, entries):
        try:
            with self.transaction() as session:
                for e in entries:
                    pe = PendingEntry(amount=e['amount'], vendor_keyword=e['vendor_keyword'])
                    session.add(pe)
                return True
        except Exception as e:
            get_logger("DB-Batch").error(f"批量插入失败: {e}")
            return False

    def add_pending_entry(self, **kwargs):
        try:
            with self.transaction() as session:
                pe = PendingEntry(**kwargs)
                session.add(pe)
                session.flush()
                return pe.id
        except Exception as e:
            get_logger("DB").error(f"影子分录入库失败: {e}")
            return None

    def update_trial_balance(self, category, amount, direction=None):
        try:
            if direction is None:
                direction = "DEBIT" if (category.startswith("1") or category.startswith("5") or "费用" in category) else "CREDIT"
            
            with self.transaction() as session:
                record = session.query(TrialBalance).filter_by(account_code=category).first()
                if record:
                    if direction == "DEBIT":
                        record.debit_total = float(record.debit_total or 0) + float(amount)
                    else:
                        record.credit_total = float(record.credit_total or 0) + float(amount)
                    record.updated_at = func.now()
                else:
                    new_balance = TrialBalance(account_code=category)
                    if direction == "DEBIT":
                        new_balance.debit_total = amount
                    else:
                        new_balance.credit_total = amount
                    session.add(new_balance)
                return True
        except Exception as e:
            get_logger("DB-Balance").error(f"更新试算平衡失败: {e}")
            return False

    def mark_transaction_reverted(self, trans_id, reason="Manual Revert"):
        try:
            with self.transaction() as session:
                trans = session.query(Transaction).filter_by(id=trans_id).first()
                if not trans: return False
                
                vendor, old_status, category, amount = trans.vendor, trans.status, trans.category, trans.amount
                
                trans.logical_revert = 1
                trans.status = 'REVERTED'
                
                if category and amount:
                    # 注意：这里需要再次开启事务或在同一个事务中调用
                    # 由于我们在 transaction() 装饰器内，这里是可以的，但 update_trial_balance 内部又开了一个 transaction
                    # 这会导致嵌套 Session 问题。
                    # 重构建议：内部方法不应该自己管理事务，或者支持传入 session。
                    # 临时方案：直接在此处更新
                    balance = session.query(TrialBalance).filter_by(account_code=category).first()
                    if balance:
                        direction = "DEBIT" if (category.startswith("1") or category.startswith("5") or "费用" in category) else "CREDIT"
                        if direction == "DEBIT":
                            balance.debit_total = float(balance.debit_total or 0) - float(amount)
                        else:
                            balance.credit_total = float(balance.credit_total or 0) - float(amount)

                if old_status in ('AUDITED', 'POSTED', 'COMPLETED'):
                    kb = session.query(KnowledgeBase).filter_by(entity_name=vendor).first()
                    if kb:
                        kb.consecutive_success = max(0, kb.consecutive_success - 1)
                        kb.hit_count = max(0, kb.hit_count - 1)
                        kb.quality_score = max(0.5, float(kb.quality_score or 1) - 0.05)
                return True
        except Exception as e:
            get_logger("DB-Revert").error(f"逻辑回撤失败: {e}")
            return False
