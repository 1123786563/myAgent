import os
import time
from core.config_manager import ConfigManager
from infra.logger import get_logger
from dotenv import load_dotenv

load_dotenv()

class DBInitializer:
    """
    [Optimization PG/SQLite] 数据库初始化逻辑 (自适应)
    """
    @staticmethod
    def init_db(db_path=None):
        db_type = os.getenv("DB_TYPE", "sqlite").lower()
        if db_type == "postgres":
            DBInitializer._init_postgres()
        else:
            DBInitializer._init_sqlite(db_path or ConfigManager.get("path.db"))

    @staticmethod
    def _init_postgres():
        import psycopg2
        pg_config = {
            "host": os.getenv("POSTGRES_HOST", "localhost"),
            "port": os.getenv("POSTGRES_PORT", "5432"),
            "user": os.getenv("POSTGRES_USER", "postgres"),
            "password": os.getenv("POSTGRES_PASSWORD", "postgres"),
            "dbname": os.getenv("POSTGRES_DBNAME", "ledger_alpha")
        }
        
        try:
            temp_conn = psycopg2.connect(host=pg_config["host"], port=pg_config["port"], 
                                         user=pg_config["user"], password=pg_config["password"], dbname="postgres")
            temp_conn.autocommit = True
            with temp_conn.cursor() as cur:
                cur.execute(f"SELECT 1 FROM pg_database WHERE datname = %s", (pg_config['dbname'],))
                if not cur.fetchone():
                    cur.execute(f"CREATE DATABASE {pg_config['dbname']}")
            temp_conn.close()
        except Exception as e:
            get_logger("DB-Init").warning(f"创建 PG 数据库失败: {e}")

        conn = psycopg2.connect(**pg_config)
        cursor = conn.cursor()
        try:
            # 基础表结构定义 (省略重复的 CREATE TABLE，实际应用中应保持完整)
            cursor.execute("CREATE TABLE IF NOT EXISTS sys_config (key TEXT PRIMARY KEY, value TEXT)")
            # ... 其他表结构 ...
            cursor.execute('''CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                status TEXT,
                amount DECIMAL(10, 2),
                vendor TEXT,
                category TEXT,
                trace_id TEXT UNIQUE, 
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                logical_revert INTEGER DEFAULT 0
            )''')
            # ...
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _init_sqlite(db_path):
        import sqlite3
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("CREATE TABLE IF NOT EXISTS sys_config (key TEXT PRIMARY KEY, value TEXT)")
            cursor.execute('''CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                status TEXT,
                amount DECIMAL(10, 2),
                vendor TEXT,
                category TEXT,
                trace_id TEXT UNIQUE, 
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                logical_revert INTEGER DEFAULT 0
            )''')
            conn.commit()
        finally:
            conn.close()
