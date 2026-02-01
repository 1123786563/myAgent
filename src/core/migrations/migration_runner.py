"""
数据库迁移运行器
Database Migration Runner
"""

import os
import importlib.util
from datetime import datetime
from typing import List, Dict, Optional
from sqlalchemy import text
from core.db_helper import DBHelper
from infra.logger import get_logger

log = get_logger("MigrationRunner")

MIGRATIONS_DIR = os.path.dirname(__file__)


class MigrationRunner:
    """数据库迁移运行器"""

    def __init__(self):
        self.db = DBHelper()

    def _ensure_migrations_table(self, conn):
        """确保迁移记录表存在"""
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS _migrations (
                id SERIAL PRIMARY KEY,
                migration_id VARCHAR(100) UNIQUE NOT NULL,
                description TEXT,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.commit()

    def _get_applied_migrations(self, conn) -> List[str]:
        """获取已应用的迁移"""
        result = conn.execute(text("SELECT migration_id FROM _migrations ORDER BY id"))
        return [row[0] for row in result.fetchall()]

    def _get_available_migrations(self) -> List[Dict]:
        """获取可用的迁移文件"""
        migrations = []
        for filename in sorted(os.listdir(MIGRATIONS_DIR)):
            if filename.endswith('.py') and filename[0].isdigit():
                filepath = os.path.join(MIGRATIONS_DIR, filename)
                spec = importlib.util.spec_from_file_location(filename[:-3], filepath)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                migrations.append({
                    'id': getattr(module, 'MIGRATION_ID', filename[:-3]),
                    'description': getattr(module, 'DESCRIPTION', ''),
                    'module': module,
                    'filename': filename
                })
        return migrations

    def status(self) -> Dict:
        """获取迁移状态"""
        engine = self.db.engine
        with engine.connect() as conn:
            self._ensure_migrations_table(conn)
            applied = self._get_applied_migrations(conn)
            available = self._get_available_migrations()

            pending = [m for m in available if m['id'] not in applied]

            return {
                'applied': applied,
                'pending': [{'id': m['id'], 'description': m['description']} for m in pending],
                'total_available': len(available)
            }

    def migrate(self, target: Optional[str] = None) -> List[str]:
        """
        执行迁移

        Args:
            target: 目标迁移ID，None表示执行所有待执行迁移
        """
        engine = self.db.engine
        applied_migrations = []

        with engine.connect() as conn:
            self._ensure_migrations_table(conn)
            applied = self._get_applied_migrations(conn)
            available = self._get_available_migrations()

            for migration in available:
                if migration['id'] in applied:
                    continue

                if target and migration['id'] != target:
                    continue

                log.info(f"Applying migration: {migration['id']} - {migration['description']}")

                try:
                    migration['module'].upgrade(engine)

                    conn.execute(
                        text("INSERT INTO _migrations (migration_id, description) VALUES (:id, :desc)"),
                        {'id': migration['id'], 'desc': migration['description']}
                    )
                    conn.commit()

                    applied_migrations.append(migration['id'])
                    log.info(f"Migration {migration['id']} applied successfully")

                except Exception as e:
                    log.error(f"Migration {migration['id']} failed: {e}")
                    raise

                if target and migration['id'] == target:
                    break

        return applied_migrations

    def rollback(self, migration_id: str) -> bool:
        """
        回滚指定迁移

        Args:
            migration_id: 要回滚的迁移ID
        """
        engine = self.db.engine

        with engine.connect() as conn:
            self._ensure_migrations_table(conn)
            applied = self._get_applied_migrations(conn)

            if migration_id not in applied:
                log.warning(f"Migration {migration_id} is not applied")
                return False

            available = self._get_available_migrations()
            migration = next((m for m in available if m['id'] == migration_id), None)

            if not migration:
                log.error(f"Migration file for {migration_id} not found")
                return False

            log.info(f"Rolling back migration: {migration_id}")

            try:
                migration['module'].downgrade(engine)

                conn.execute(
                    text("DELETE FROM _migrations WHERE migration_id = :id"),
                    {'id': migration_id}
                )
                conn.commit()

                log.info(f"Migration {migration_id} rolled back successfully")
                return True

            except Exception as e:
                log.error(f"Rollback of {migration_id} failed: {e}")
                raise

    def reset(self) -> List[str]:
        """回滚所有迁移"""
        engine = self.db.engine
        rolled_back = []

        with engine.connect() as conn:
            self._ensure_migrations_table(conn)
            applied = self._get_applied_migrations(conn)

            # 按逆序回滚
            for migration_id in reversed(applied):
                if self.rollback(migration_id):
                    rolled_back.append(migration_id)

        return rolled_back


def run_migrations():
    """运行所有待执行的迁移"""
    runner = MigrationRunner()
    status = runner.status()

    if not status['pending']:
        log.info("No pending migrations")
        return []

    log.info(f"Found {len(status['pending'])} pending migrations")
    return runner.migrate()


if __name__ == "__main__":
    import sys

    runner = MigrationRunner()

    if len(sys.argv) < 2:
        print("Usage: python migration_runner.py [status|migrate|rollback <id>|reset]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "status":
        status = runner.status()
        print(f"\nApplied migrations: {len(status['applied'])}")
        for m in status['applied']:
            print(f"  ✓ {m}")
        print(f"\nPending migrations: {len(status['pending'])}")
        for m in status['pending']:
            print(f"  ○ {m['id']}: {m['description']}")

    elif command == "migrate":
        applied = runner.migrate()
        print(f"\nApplied {len(applied)} migrations")

    elif command == "rollback" and len(sys.argv) > 2:
        migration_id = sys.argv[2]
        if runner.rollback(migration_id):
            print(f"Rolled back: {migration_id}")
        else:
            print(f"Failed to rollback: {migration_id}")

    elif command == "reset":
        rolled_back = runner.reset()
        print(f"Rolled back {len(rolled_back)} migrations")

    else:
        print("Unknown command")
        sys.exit(1)
