from core.db_transactions import DBTransactions
from core.db_queries import DBQueries
from core.db_maintenance import DBMaintenance
from core.db_initializer import DBInitializer

class DBHelper(DBTransactions, DBQueries, DBMaintenance):
    """
    [Optimization Iteration 4] 增强型数据库助手 (聚合类)
    """
    def __init__(self):
        super().__init__()
        # Initializing the database if not already done
        DBInitializer.init_db(self.db_path)

    def update_heartbeat(self, service_name, status="OK", owner_id=None, metrics=None):
        with self.transaction("IMMEDIATE") as conn:
            conn.execute('''
                INSERT OR REPLACE INTO sys_status (service_name, last_heartbeat, status, metrics)
                VALUES (?, CURRENT_TIMESTAMP, ?, ?)
            ''', (service_name, status, metrics))

    def log_system_event(self, event_type, service_name, message, trace_id=None):
        try:
            with self.transaction("IMMEDIATE") as conn:
                conn.execute('''
                    INSERT INTO system_events (event_type, service_name, message, trace_id)
                    VALUES (?, ?, ?, ?)
                ''', (event_type, service_name, message, trace_id))
        except:
            pass

    def check_health(self, service_name, timeout_seconds=60):
        sql = """
            SELECT (strftime('%s','now') - strftime('%s', last_heartbeat)) < ? as healthy
            FROM sys_status WHERE service_name = ?
        """
        try:
            with self.transaction("DEFERRED") as conn:
                res = conn.execute(sql, (timeout_seconds, service_name)).fetchone()
                return bool(res['healthy']) if res else False
        except:
            return False

    def get_now(self):
        import datetime
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def acquire_business_lock(self, service_name, owner_id):
        with self.transaction("IMMEDIATE") as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE sys_status 
                SET lock_owner = ?, last_heartbeat = CURRENT_TIMESTAMP
                WHERE service_name = ? AND (lock_owner IS NULL OR lock_owner = ?)
            ''', (owner_id, service_name, owner_id))
            return cursor.rowcount > 0
    
    # Legacy support / convenience aliases
    def add_transaction_with_tags(self, tags=None, **kwargs):
        return self.add_transaction_with_chain(tags=tags, **kwargs)

    def verify_ledger_chain(self):
        success, msg = self.verify_chain_integrity()
        if not success:
            self.log_system_event("CHAIN_CORRUPT", "DB", f"检测到账本哈希链中断: {msg}")
            return False, msg
        return True, "Verified"
