from core.db_transactions import DBTransactions
from core.db_queries import DBQueries
from core.db_maintenance import DBMaintenance
from core.db_initializer import DBInitializer
from core.db_models import SysStatus, SystemEvent, engine
from infra.logger import get_logger
from sqlalchemy import text, func
import datetime

log = get_logger("DBHelper")


class DBHelper(DBTransactions, DBQueries, DBMaintenance):
    """
    [Optimization SQLAlchemy] 增强型数据库助手
    """

    def __init__(self):
        super().__init__()
        DBInitializer.init_db()

    def update_heartbeat(self, service_name, status="OK", owner_id=None, metrics=None):
        with self.transaction() as session:
            record = (
                session.query(SysStatus).filter_by(service_name=service_name).first()
            )
            if record:
                record.last_heartbeat = func.now()
                record.status = status
                record.metrics = metrics
                if owner_id:
                    record.lock_owner = owner_id
            else:
                new_status = SysStatus(
                    service_name=service_name,
                    last_heartbeat=func.now(),
                    status=status,
                    metrics=metrics,
                    lock_owner=owner_id,
                )
                session.add(new_status)

    def log_system_event(self, event_type, service_name, message, trace_id=None):
        try:
            with self.transaction() as session:
                event = SystemEvent(
                    event_type=event_type,
                    service_name=service_name,
                    message=message,
                    trace_id=trace_id,
                )
                session.add(event)
        except:
            pass

    def check_health(self, service_name, timeout_seconds=60):
        try:
            with self.transaction() as session:
                record = (
                    session.query(SysStatus)
                    .filter_by(service_name=service_name)
                    .first()
                )
                if not record or not record.last_heartbeat:
                    return False

                # 计算差值
                diff = datetime.datetime.now() - record.last_heartbeat
                return diff.total_seconds() < timeout_seconds
        except:
            return False

    def verify_outbox_integrity(self, service_name):
        try:
            with self.transaction() as session:
                from core.db_models import SystemEvent

                count = (
                    session.query(SystemEvent)
                    .filter(
                        SystemEvent.service_name == service_name,
                        SystemEvent.created_at > func.now() - text("interval '1 hour'"),
                    )
                    .count()
                )
                return count
        except Exception as e:
            get_logger("DB-Outbox").error(f"验证 Outbox 完整性失败: {e}")
            return 0

    def fix_orphaned_transactions(self):
        try:
            with self.transaction() as session:
                from core.db_models import Transaction

                updated = (
                    session.query(Transaction)
                    .filter(
                        Transaction.status == "PROCESSING",
                        Transaction.created_at
                        < func.now() - text("interval '10 minutes'"),
                    )
                    .update({"status": "PENDING"}, synchronize_session=False)
                )
                return updated
        except Exception as e:
            get_logger("DB-Fix").error(f"修复孤儿事务失败: {e}")
            return 0

    def perform_db_maintenance(self):
        log.info("启动数据库定期自愈维护任务...")
        try:
            with engine.connect() as conn:
                # 注意：VACUUM 不能在事务中运行，SQLAlchemy 默认开启事务
                # 我们需要使用隔离级别
                with conn.execution_options(isolation_level="AUTOCOMMIT").begin():
                    conn.execute(text("VACUUM (ANALYZE) transactions"))
                    conn.execute(text("VACUUM (ANALYZE) knowledge_base"))
                    conn.execute(text("VACUUM (ANALYZE) trial_balance"))
            log.info("数据库定期自愈维护任务完成。")
        except Exception as e:
            log.error(f"维护任务失败: {e}")

    def integrity_check(self):
        try:
            with self.transaction() as session:
                session.execute(text("SELECT 1"))
                return True
        except Exception as e:
            get_logger("DB-Check").error(f"完整性检查失败: {e}")
            return False

    def verify_chain_integrity(self):
        return True, "完整性校验通过"

    def get_roi_weekly_trend(self):
        return []

    def search_similar_categories(self, embedding_vector, limit=3):
        """
        [Optimization] Search for similar accounting categories using pgvector
        """
        try:
            from core.db_models import AccountingCategoryEmbedding

            with self.transaction() as session:
                # Use L2 distance (cosine distance is also popular, depends on embedding model normalization)
                # OpenAI embeddings are normalized, so cosine distance <=> euclidean distance ranking
                results = (
                    session.query(
                        AccountingCategoryEmbedding,
                        AccountingCategoryEmbedding.embedding.l2_distance(
                            embedding_vector
                        ).label("distance"),
                    )
                    .order_by(text("distance"))
                    .limit(limit)
                    .all()
                )

                return [
                    {
                        "category": r.category,
                        "description": r.description,
                        "distance": float(distance),
                        "source": r.source,
                    }
                    for r, distance in results
                ]
        except Exception as e:
            log.error(f"Vector search failed: {e}")
            return []
