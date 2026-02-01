from core.db_transactions import DBTransactions
from core.db_queries import DBQueries
from core.db_maintenance import DBMaintenance
from core.db_initializer import DBInitializer

class DBHelper(DBTransactions, DBQueries, DBMaintenance):
    """
    [Optimization Iteration PG] 增强型数据库助手 (聚合类)
    """
    def __init__(self):
        super().__init__()
        DBInitializer.init_db()

    def _execute(self, sql, params=()):
        with self.transaction() as conn:
            if self.db_type == "postgres":
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    return cur
            else:
                return conn.execute(sql, params)

    def update_heartbeat(self, service_name, status="OK", owner_id=None, metrics=None):
        p = self._get_placeholder()
        if self.db_type == "postgres":
            sql = f'''
                INSERT INTO sys_status (service_name, last_heartbeat, status, metrics)
                VALUES ({p}, CURRENT_TIMESTAMP, {p}, {p})
                ON CONFLICT (service_name) DO UPDATE SET
                    last_heartbeat = EXCLUDED.last_heartbeat,
                    status = EXCLUDED.status,
                    metrics = EXCLUDED.metrics
            '''
        else:
            sql = f'''
                INSERT OR REPLACE INTO sys_status (service_name, last_heartbeat, status, metrics)
                VALUES ({p}, CURRENT_TIMESTAMP, {p}, {p})
            '''
        self._execute(sql, (service_name, status, metrics))

    def log_system_event(self, event_type, service_name, message, trace_id=None):
        p = self._get_placeholder()
        sql = f'''
            INSERT INTO system_events (event_type, service_name, message, trace_id)
            VALUES ({p}, {p}, {p}, {p})
        '''
        try:
            self._execute(sql, (event_type, service_name, message, trace_id))
        except:
            pass

    def check_health(self, service_name, timeout_seconds=60):
        p = self._get_placeholder()
        if self.db_type == "postgres":
            sql = f"SELECT (extract(epoch from now()) - extract(epoch from last_heartbeat)) < {p} FROM sys_status WHERE service_name = {p}"
        else:
            sql = f"SELECT (strftime('%s','now') - strftime('%s', last_heartbeat)) < {p} FROM sys_status WHERE service_name = {p}"
        
        try:
            res = self._execute(sql, (timeout_seconds, service_name))
            if self.db_type == "postgres":
                row = res.fetchone()
                return bool(row[0]) if row else False
            else:
                row = res.fetchone()
                return bool(row[0]) if row else False
        except:
            return False

    def get_now(self):
        import datetime
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def acquire_business_lock(self, service_name, owner_id):
        p = self._get_placeholder()
        sql = f'''
            UPDATE sys_status 
            SET lock_owner = {p}, last_heartbeat = CURRENT_TIMESTAMP
            WHERE service_name = {p} AND (lock_owner IS NULL OR lock_owner = {p})
        '''
        res = self._execute(sql, (owner_id, service_name, owner_id))
        return res.rowcount > 0
