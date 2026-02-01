import os
import time
from core.config_manager import ConfigManager
from infra.logger import get_logger
from dotenv import load_dotenv

load_dotenv()

class DBInitializer:
    """
    [Optimization PG Only] 数据库初始化逻辑 (仅支持 PostgreSQL)
    """
    @staticmethod
    def init_db():
        DBInitializer._init_postgres()

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
            # 建立到默认数据库 'postgres' 的连接，以确保目标数据库存在
            temp_conn = psycopg2.connect(host=pg_config["host"], port=pg_config["port"], 
                                         user=pg_config["user"], password=pg_config["password"], dbname="postgres")
            temp_conn.autocommit = True
            with temp_conn.cursor() as cur:
                cur.execute(f"SELECT 1 FROM pg_database WHERE datname = %s", (pg_config['dbname'],))
                if not cur.fetchone():
                    cur.execute(f"CREATE DATABASE {pg_config['dbname']}")
            temp_conn.close()
        except Exception as e:
            get_logger("DB-Init").warning(f"确保 PG 数据库存在时遇到问题: {e}")

        conn = psycopg2.connect(**pg_config)
        cursor = conn.cursor()
        try:
            # 基础表结构定义
            cursor.execute("CREATE TABLE IF NOT EXISTS sys_config (key TEXT PRIMARY KEY, value TEXT)")
            cursor.execute("CREATE TABLE IF NOT EXISTS sys_status (service_name TEXT PRIMARY KEY, last_heartbeat TIMESTAMP, status TEXT, metrics JSONB, lock_owner TEXT)")
            cursor.execute("CREATE TABLE IF NOT EXISTS system_events (id SERIAL PRIMARY KEY, event_type TEXT, service_name TEXT, message TEXT, trace_id TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
            
            # [Fix Round 12] 确保所有字段存在 (SQLite 迁移遗留)
            cursor.execute('''CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                status TEXT,
                amount DECIMAL(10, 2),
                vendor TEXT,
                category TEXT,
                trace_id TEXT UNIQUE, 
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                logical_revert INTEGER DEFAULT 0,
                prev_hash TEXT,
                chain_hash TEXT,
                inference_log JSONB,
                group_id TEXT
            )''')
            
            cursor.execute("CREATE TABLE IF NOT EXISTS transaction_tags (id SERIAL PRIMARY KEY, transaction_id INTEGER REFERENCES transactions(id), tag_key TEXT, tag_value TEXT)")
            
            # [Fix] pending_entries 增加 status 字段
            cursor.execute('''CREATE TABLE IF NOT EXISTS pending_entries (
                id SERIAL PRIMARY KEY, 
                amount DECIMAL(10, 2), 
                vendor_keyword TEXT, 
                status TEXT DEFAULT 'PENDING',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
            
            cursor.execute("CREATE TABLE IF NOT EXISTS trial_balance (account_code TEXT PRIMARY KEY, debit_total DECIMAL(15, 2) DEFAULT 0, credit_total DECIMAL(15, 2) DEFAULT 0, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
            cursor.execute("CREATE TABLE IF NOT EXISTS roi_metrics_history (report_date DATE PRIMARY KEY, human_hours_saved DECIMAL(10, 2), token_spend_usd DECIMAL(10, 4), roi_ratio DECIMAL(10, 2))")
            
            # [Fix] knowledge_base 增加 id, audit_status, category_mapping, reject_count, updated_at
            cursor.execute('''CREATE TABLE IF NOT EXISTS knowledge_base (
                id SERIAL PRIMARY KEY,
                entity_name TEXT UNIQUE, 
                category_mapping TEXT,
                audit_status TEXT DEFAULT 'GRAY',
                consecutive_success INTEGER DEFAULT 0, 
                reject_count INTEGER DEFAULT 0,
                hit_count INTEGER DEFAULT 0, 
                quality_score DECIMAL(3, 2) DEFAULT 1.0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
            
            # 索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trans_status ON transactions (status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trans_vendor ON transactions (vendor)")
            
            # 创建视图 (如果不存在)
            cursor.execute('''
                CREATE OR REPLACE VIEW v_knowledge_conflicts AS
                SELECT entity_name FROM knowledge_base 
                GROUP BY entity_name HAVING COUNT(DISTINCT category_mapping) > 1
            ''')
            
            conn.commit()
        except Exception as e:
            get_logger("DB-Init").error(f"初始化 PG 表结构失败: {e}")
            conn.rollback()
        finally:
            conn.close()
