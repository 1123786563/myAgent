from core.db_transactions import DBTransactions
from core.db_queries import DBQueries
from core.db_maintenance import DBMaintenance
from core.db_initializer import DBInitializer
import psycopg2.extras

class DBHelper(DBTransactions, DBQueries, DBMaintenance):
    """
    [Optimization Iteration PG] 增强型数据库助手 (仅支持 PostgreSQL)
    """
    def __init__(self):
        super().__init__()
        DBInitializer.init_db()

    def _execute(self, sql, params=()):
        with self.transaction() as conn:
            # 使用 DictCursor 使得可以通过列名访问结果，类似 SQLite Row
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute(sql, params)
            return cur

    def update_heartbeat(self, service_name, status="OK", owner_id=None, metrics=None):
        sql = '''
            INSERT INTO sys_status (service_name, last_heartbeat, status, metrics)
            VALUES (%s, CURRENT_TIMESTAMP, %s, %s)
            ON CONFLICT (service_name) DO UPDATE SET
                last_heartbeat = EXCLUDED.last_heartbeat,
                status = EXCLUDED.status,
                metrics = EXCLUDED.metrics
        '''
        self._execute(sql, (service_name, status, metrics))

    def log_system_event(self, event_type, service_name, message, trace_id=None):
        sql = '''
            INSERT INTO system_events (event_type, service_name, message, trace_id)
            VALUES (%s, %s, %s, %s)
        '''
        try:
            self._execute(sql, (event_type, service_name, message, trace_id))
        except:
            pass

    def check_health(self, service_name, timeout_seconds=60):
        sql = "SELECT (extract(epoch from now()) - extract(epoch from last_heartbeat)) < %s FROM sys_status WHERE service_name = %s"
        
        try:
            res = self._execute(sql, (timeout_seconds, service_name))
            row = res.fetchone()
            return bool(row[0]) if row else False
        except:
            return False

    def get_now(self):
        import datetime
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def acquire_business_lock(self, service_name, owner_id):
        sql = '''
            UPDATE sys_status 
            SET lock_owner = %s, last_heartbeat = CURRENT_TIMESTAMP
            WHERE service_name = %s AND (lock_owner IS NULL OR lock_owner = %s)
        '''
        res = self._execute(sql, (owner_id, service_name, owner_id))
        return res.rowcount > 0
