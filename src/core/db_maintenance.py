import shutil
import uuid
import hashlib
import json
from core.db_base import DBBase
from infra.logger import get_logger

class DBMaintenance(DBBase):
    """
    [Optimization 5/16] 数据库定期自愈保养与维护
    """
    def perform_db_maintenance(self):
        try:
            get_logger("DB-Maintenance").info("启动数据库定期自愈维护任务...")
            self.trigger_wal_checkpoint()
            with self.transaction("DEFERRED") as conn:
                conn.execute("ANALYZE")
            get_logger("DB-Maintenance").info("数据库维护完成：WAL 已刷回，统计信息已更新。")
            return True
        except Exception as e:
            get_logger("DB").error(f"维护任务失败: {e}")
            return False

    def backup_db(self, backup_path):
        try:
            with self.transaction("DEFERRED") as conn:
                conn.execute(f"VACUUM INTO '{backup_path}'")
            return True
        except Exception as e:
            print(f"备份失败: {e}")
            return False

    def create_snapshot(self, description=""):
        snapshot_id = f"SNAP-{uuid.uuid4().hex[:8].upper()}"
        snapshot_path = self.db_path + f".{snapshot_id}"
        try:
            self.trigger_wal_checkpoint()
            shutil.copy2(self.db_path, snapshot_path)
            # system event logging should be handled by a higher level or shared method
            get_logger("DB").info(f"成功创建数据库快照: {snapshot_id} | 描述: {description}")
            return snapshot_id
        except Exception as e:
            get_logger("DB").error(f"创建快照失败: {e}")
            return None

    def verify_chain_integrity(self):
        try:
            with self.transaction("DEFERRED") as conn:
                rows = conn.execute("SELECT id, amount, vendor, trace_id, prev_hash, chain_hash FROM transactions ORDER BY id ASC").fetchall()
                expected_prev = "0" * 64
                for row in rows:
                    if row['prev_hash'] != expected_prev:
                        return False, f"链条中断: ID {row['id']} 期望 prev_hash {expected_prev}, 实际 {row['prev_hash']}"
                    data_to_hash = {
                        "trace_id": row['trace_id'],
                        "amount": str(row['amount']),
                        "vendor": row['vendor'],
                        "prev_hash": row['prev_hash']
                    }
                    calc_hash = hashlib.sha256(json.dumps(data_to_hash, sort_keys=True).encode()).hexdigest()
                    if calc_hash != row['chain_hash']:
                        return False, f"哈希校验失败: ID {row['id']} 数据可能被篡改"
                    expected_prev = row['chain_hash']
                return True, "完整性校验通过"
        except Exception as e:
            return False, str(e)

    def vacuum(self):
        try:
            conn = self._get_conn()
            conn.execute("VACUUM")
            return True
        except Exception:
            return False

    def fix_orphaned_transactions(self):
        try:
            with self.transaction("IMMEDIATE") as conn:
                sql = "UPDATE transactions SET status = 'PENDING' WHERE status = 'MATCHING' AND datetime(created_at) < datetime('now', '-1 hour')"
                res = conn.execute(sql)
                return res.rowcount
        except Exception:
            return 0
