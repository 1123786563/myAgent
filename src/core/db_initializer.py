import sqlite3
import time
from core.config_manager import ConfigManager
from infra.logger import get_logger

class DBInitializer:
    """
    [Optimization 2] 增强数据库启动自愈逻辑
    [Optimization Round 7] 增加 Schema 版本管理与自动迁移
    """
    @staticmethod
    def init_db(db_path):
        CURRENT_SCHEMA_VERSION = 10
        conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            cursor.execute("BEGIN IMMEDIATE")
            
            cursor.execute("CREATE TABLE IF NOT EXISTS sys_config (key TEXT PRIMARY KEY, value TEXT)")
            cursor.execute("SELECT value FROM sys_config WHERE key = 'schema_version'")
            row = cursor.fetchone()
            version = int(row['value']) if row else 0
            
            if version < CURRENT_SCHEMA_VERSION:
                cursor.execute("INSERT OR REPLACE INTO sys_config (key, value) VALUES ('schema_version', ?)", (str(CURRENT_SCHEMA_VERSION),))

            # [Iteration 6] 逻辑回撤支持
            try:
                cursor.execute("ALTER TABLE transactions ADD COLUMN logical_revert INTEGER DEFAULT 0")
            except sqlite3.OperationalError: pass

            # [Iteration 10] 禁止更新已回撤数据的触发器
            cursor.execute('''
                CREATE TRIGGER IF NOT EXISTS trg_prevent_update_reverted
                BEFORE UPDATE ON transactions
                FOR EACH ROW
                WHEN OLD.logical_revert = 1
                BEGIN
                    SELECT RAISE(ABORT, 'Cannot update a logically reverted transaction');
                END;
            ''')

            # [Iteration 11] 禁止删除记录的触发器（证据持久化保护）
            cursor.execute('''
                CREATE TRIGGER IF NOT EXISTS trg_prevent_delete_transactions
                BEFORE DELETE ON transactions
                BEGIN
                    SELECT RAISE(ABORT, 'Physical deletion is prohibited. Use logical_revert instead.');
                END;
            ''')

            # [Iteration 11] 为 group_id 增加索引以提升关联性分析性能
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trans_group ON transactions(group_id)")

            # [Optimization 1] 全局试算平衡表 (Trial Balance)
            cursor.execute('''CREATE TABLE IF NOT EXISTS trial_balance (
                account_code TEXT PRIMARY KEY,
                debit_total DECIMAL(15, 2) DEFAULT 0,
                credit_total DECIMAL(15, 2) DEFAULT 0,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )''')

            # [Optimization 3] 预算管理表 (F3.3.3)
            cursor.execute('''CREATE TABLE IF NOT EXISTS dept_budgets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dept_name TEXT UNIQUE,
                monthly_limit DECIMAL(10, 2),
                current_spent DECIMAL(10, 2) DEFAULT 0,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )''')

            # [Optimization 5] 效益历史指标表 (F4.2)
            cursor.execute('''CREATE TABLE IF NOT EXISTS roi_metrics_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_date DATE DEFAULT (DATE('now')),
                human_hours_saved REAL,
                token_spend_usd REAL,
                roi_ratio REAL,
                accuracy_gain REAL DEFAULT 0,
                UNIQUE(report_date)
            )''')

            # [Optimization 2] 税务政策参数表 (F3.3.1)
            cursor.execute('''CREATE TABLE IF NOT EXISTS tax_policies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                policy_key TEXT UNIQUE,
                policy_value REAL,
                description TEXT,
                version INTEGER DEFAULT 1,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )''')
            
            cursor.executemany("INSERT OR IGNORE INTO tax_policies (policy_key, policy_value, description) VALUES (?, ?, ?)", [
                ("vat_rate_general", 0.13, "一般纳税人增值税率"),
                ("vat_rate_small", 0.03, "小规模纳税人征收率"),
                ("tax_free_limit", 100000.0, "月度免税额度")
            ])

            cursor.execute('''CREATE VIEW IF NOT EXISTS v_asset_summary AS
                SELECT 
                    group_id, 
                    vendor, 
                    SUM(amount) as total_value, 
                    COUNT(*) as attachment_count,
                    GROUP_CONCAT(file_path, '|') as file_paths,
                    MIN(created_at) as first_seen,
                    MAX(created_at) as last_updated
                FROM transactions 
                WHERE group_id IS NOT NULL
                GROUP BY group_id
            ''')

            cursor.execute('''CREATE TABLE IF NOT EXISTS evidence_chain_index (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_id INTEGER,
                step_name TEXT,
                evidence_type TEXT, 
                evidence_data TEXT, 
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(transaction_id) REFERENCES transactions(id)
            )''')

            cursor.execute('''CREATE VIEW IF NOT EXISTS v_pivot_analysis AS
                SELECT 
                    t.id as trans_id, t.vendor, t.amount, t.category, t.status,
                    MAX(CASE WHEN tg.tag_key = 'project_id' THEN tg.tag_value END) as project,
                    MAX(CASE WHEN tg.tag_key = 'department' THEN tg.tag_value END) as department
                FROM transactions t
                LEFT JOIN transaction_tags tg ON t.id = tg.transaction_id
                GROUP BY t.id
            ''')

            cursor.execute('''CREATE VIEW IF NOT EXISTS v_knowledge_conflicts AS
                SELECT entity_name, COUNT(DISTINCT category_mapping) as cat_count
                FROM knowledge_base 
                WHERE audit_status = 'GRAY'
                GROUP BY entity_name
                HAVING cat_count > 1
            ''')

            cursor.execute('''CREATE TABLE IF NOT EXISTS sys_permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role_name TEXT,
                action_name TEXT,
                UNIQUE(role_name, action_name)
            )''')

            cursor.execute('''CREATE TABLE IF NOT EXISTS sys_permission_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operator_role TEXT,
                action_performed TEXT,
                details TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )''')
            
            default_perms = [
                ("ACCOUNTANT", "PROPOSE_ENTRY"),
                ("AUDITOR", "AUDIT_RESULT"),
                ("SENTINEL", "SENTINEL_CHECK"),
                ("MASTER", "HEARTBEAT")
            ]
            cursor.executemany("INSERT OR IGNORE INTO sys_permissions (role_name, action_name) VALUES (?, ?)", default_perms)
            
            journal_size_limit = ConfigManager.get("db.journal_size_limit", 67108864)
            cursor.execute(f"PRAGMA journal_size_limit = {journal_size_limit}")
            cursor.execute("PRAGMA auto_vacuum = INCREMENTAL")
            
            DBInitializer._daily_maintenance(cursor)

            cursor.execute('''CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                status TEXT,
                source_type TEXT,
                amount DECIMAL(10, 2),
                currency TEXT DEFAULT 'CNY',
                vendor TEXT,
                category TEXT,
                trace_id TEXT UNIQUE, 
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                file_path TEXT,
                file_hash TEXT UNIQUE,
                inference_log TEXT, 
                reasoning_graph TEXT, 
                group_id TEXT,      
                prev_hash TEXT,     
                chain_hash TEXT     
            )''')

            cursor.execute('''CREATE TABLE IF NOT EXISTS transaction_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_id INTEGER,
                tag_key TEXT,
                tag_value TEXT,
                FOREIGN KEY(transaction_id) REFERENCES transactions(id)
            )''')
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tag_kv ON transaction_tags(tag_key, tag_value)")

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trans_status ON transactions(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trans_vendor ON transactions(vendor)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trans_trace ON transactions(trace_id)")

            cursor.execute('''CREATE TABLE IF NOT EXISTS pending_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                amount DECIMAL(10, 2),
                vendor_keyword TEXT,
                status TEXT DEFAULT 'PENDING',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )''')
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_pending_status ON pending_entries(status)")

            cursor.execute('''CREATE TABLE IF NOT EXISTS knowledge_base (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_name TEXT UNIQUE,
                category_mapping TEXT,
                hit_count INTEGER DEFAULT 0,
                reject_count INTEGER DEFAULT 0,
                audit_status TEXT DEFAULT 'GRAY', 
                consecutive_success INTEGER DEFAULT 0,
                audit_level TEXT DEFAULT 'NORMAL', 
                quality_score REAL DEFAULT 1.0, 
                last_used_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )''')

            cursor.execute('''CREATE VIEW IF NOT EXISTS v_audit_trail AS
                SELECT 
                    t.id as trans_id, t.created_at, t.vendor, t.amount, t.category, t.status,
                    t.inference_log,
                    GROUP_CONCAT(tg.tag_key || ':' || tg.tag_value, '|') as tags
                FROM transactions t
                LEFT JOIN transaction_tags tg ON t.id = tg.transaction_id
                GROUP BY t.id
            ''')
            
            try:
                cursor.execute("CREATE VIRTUAL TABLE IF NOT EXISTS kb_fts USING fts5(entity_name, content='knowledge_base', content_rowid='id')")
                cursor.execute('''CREATE TRIGGER IF NOT EXISTS kb_ai AFTER INSERT ON knowledge_base BEGIN
                                  INSERT INTO kb_fts(rowid, entity_name) VALUES (new.id, new.entity_name);
                                END;''')
            except sqlite3.OperationalError:
                pass
            
            cursor.execute('''CREATE TABLE IF NOT EXISTS sys_status (
                service_name TEXT PRIMARY KEY,
                last_heartbeat DATETIME DEFAULT CURRENT_TIMESTAMP,
                status TEXT,
                panic_msg TEXT, 
                metrics TEXT 
            )''')

            cursor.execute('''CREATE TABLE IF NOT EXISTS system_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT,
                service_name TEXT,
                message TEXT,
                trace_id TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )''')
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_event_type ON system_events(event_type)")

            cursor.execute('''CREATE TABLE IF NOT EXISTS export_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                export_id TEXT UNIQUE,
                filename TEXT,
                record_count INTEGER,
                operator TEXT,
                filters TEXT, 
                status TEXT, 
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )''')
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_export_operator ON export_audit(operator)")
            
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"CRITICAL: 数据库初始化失败: {e}")
        finally:
            conn.close()

    @staticmethod
    def _daily_maintenance(cursor):
        try:
            today = time.strftime("%Y-%m-%d")
            cursor.execute("CREATE TABLE IF NOT EXISTS sys_maintenance (task_name TEXT PRIMARY KEY, last_run TEXT)")
            
            cursor.execute("SELECT last_run FROM sys_maintenance WHERE task_name = 'integrity_check'")
            row = cursor.fetchone()
            if not row or row['last_run'] != today:
                print(f"[{today}] 执行数据库完整性检查与统计信息更新...")
                cursor.execute("PRAGMA integrity_check")
                res = cursor.fetchone()
                cursor.execute("ANALYZE")
                
                if res and res[0] == "ok":
                    cursor.execute("INSERT OR REPLACE INTO sys_maintenance (task_name, last_run) VALUES ('integrity_check', ?)", (today,))
                else:
                    print(f"警告：数据库完整性检查未通过！{res}")
        except Exception as e:
            print(f"维护任务异常: {e}")
