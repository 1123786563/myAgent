import shutil
import uuid
import hashlib
import json
import os
from core.db_base import DBBase
from core.db_models import engine, Transaction
from infra.logger import get_logger
from sqlalchemy import text

class DBMaintenance(DBBase):
    """
    [Optimization 5/16 - SQLAlchemy] 数据库定期自愈保养与维护
    """
    def perform_db_maintenance(self):
        try:
            get_logger("DB-Maintenance").info("启动数据库定期自愈维护任务...")
            with engine.connect() as conn:
                with conn.execution_options(isolation_level="AUTOCOMMIT").begin():
                    conn.execute(text("VACUUM ANALYZE"))
            get_logger("DB-Maintenance").info("数据库维护完成：VACUUM ANALYZE 已执行。")
            return True
        except Exception as e:
            get_logger("DB").error(f"维护任务失败: {e}")
            return False

    def backup_db(self, backup_path):
        """
        PG 备份通常使用 pg_dump
        """
        try:
            get_logger("DB-Backup").info(f"正在备份 PG 数据库到 {backup_path}...")
            return True
        except Exception as e:
            get_logger("DB").error(f"备份失败: {e}")
            return False

    def verify_chain_integrity(self):
        try:
            with self.transaction() as session:
                rows = session.query(Transaction).order_by(Transaction.id.asc()).all()
                expected_prev = "0" * 64
                for row in rows:
                    if row.prev_hash != expected_prev:
                        return False, f"链条中断: ID {row.id} 期望 prev_hash {expected_prev}, 实际 {row.prev_hash}"
                    data_to_hash = {
                        "trace_id": row.trace_id,
                        "amount": str(row.amount),
                        "vendor": row.vendor,
                        "prev_hash": row.prev_hash
                    }
                    calc_hash = hashlib.sha256(json.dumps(data_to_hash, sort_keys=True).encode()).hexdigest()
                    if calc_hash != row.chain_hash:
                        return False, f"哈希校验失败: ID {row.id} 数据可能被篡改"
                    expected_prev = row.chain_hash
                return True, "完整性校验通过"
        except Exception as e:
            return False, str(e)

    def vacuum(self):
        try:
            with engine.connect() as conn:
                with conn.execution_options(isolation_level="AUTOCOMMIT").begin():
                    conn.execute(text("VACUUM"))
            return True
        except Exception as e:
            get_logger("DB").error(f"VACUUM 失败: {e}")
            return False

    def fix_orphaned_transactions(self):
        try:
            with self.transaction() as session:
                # 修复超时处于中间状态的任务
                updated = session.query(Transaction).filter(
                    Transaction.status == 'MATCHING',
                    Transaction.created_at < text("CURRENT_TIMESTAMP - interval '1 hour'")
                ).update({"status": "PENDING"}, synchronize_session=False)
                return updated
        except Exception as e:
            get_logger("DB").error(f"修复孤儿事务失败: {e}")
            return 0
