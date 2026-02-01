from core.db_models import engine, Base
from infra.logger import get_logger
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

class DBInitializer:
    """
    [Optimization SQLAlchemy] 数据库初始化逻辑
    """
    @staticmethod
    def init_db():
        DBInitializer._ensure_db_exists()
        DBInitializer._init_tables()

    @staticmethod
    def _ensure_db_exists():
        pg_host = os.getenv("POSTGRES_HOST", "localhost")
        pg_port = os.getenv("POSTGRES_PORT", "5432")
        pg_user = os.getenv("POSTGRES_USER", "postgres")
        pg_pass = os.getenv("POSTGRES_PASSWORD", "postgres")
        pg_dbname = os.getenv("POSTGRES_DBNAME", "ledger_alpha")
        
        try:
            temp_conn = psycopg2.connect(host=pg_host, port=pg_port, 
                                         user=pg_user, password=pg_pass, dbname="postgres")
            temp_conn.autocommit = True
            with temp_conn.cursor() as cur:
                cur.execute(f"SELECT 1 FROM pg_database WHERE datname = %s", (pg_dbname,))
                if not cur.fetchone():
                    cur.execute(f"CREATE DATABASE {pg_dbname}")
            temp_conn.close()
        except Exception as e:
            get_logger("DB-Init").warning(f"确保 PG 数据库存在时遇到问题: {e}")

    @staticmethod
    def _init_tables():
        try:
            Base.metadata.create_all(bind=engine)
            get_logger("DB-Init").info("SQLAlchemy 表结构初始化完成。")
        except Exception as e:
            get_logger("DB-Init").error(f"初始化表结构失败: {e}")
