import sqlite3
import threading
import time
from contextlib import contextmanager
from config_manager import ConfigManager
from project_paths import get_path

class DBHelper:
    _instance = None
    _lock = threading.Lock()
    _local = threading.local()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DBHelper, cls).__new__(cls)
                cls._instance.db_path = ConfigManager.get("path.db")
                cls._instance._init_db()
        return cls._instance

    def _get_conn(self):
        if not hasattr(self._local, "conn") or self._local.conn is None:
            # 优化点：从配置中心加载数据库性能参数
            busy_timeout = ConfigManager.get("db.busy_timeout", 30000)
            journal_mode = ConfigManager.get("db.journal_mode", "WAL")
            
            conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=busy_timeout/1000)
            conn.row_factory = sqlite3.Row
            conn.execute(f"PRAGMA journal_mode={journal_mode}")
            self._local.conn = conn
            # 优化点：初始化预编译语句缓存
            self._local.statement_cache = {}
        return self._local.conn

    def _get_cursor(self, sql):
        """获取带缓存的游标对象"""
        conn = self._get_conn()
        if sql not in self._local.statement_cache:
            # 限制缓存大小防止内存溢出
            if len(self._local.statement_cache) > 100:
                self._local.statement_cache.pop(next(iter(self._local.statement_cache)))
            self._local.statement_cache[sql] = conn.cursor()
        return self._local.statement_cache[sql]

    @contextmanager
    def transaction(self, mode="DEFERRED"):
        retry_count = ConfigManager.get("db.retry_count", 5)
        base_delay = ConfigManager.get("db.retry_delay", 0.1)
        import random
        last_error = None
        
        for i in range(retry_count):
            try:
                conn = self._get_conn()
                conn.execute(f"BEGIN {mode}")
                yield conn
                conn.commit()
                return
            except sqlite3.OperationalError as e:
                last_error = e
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    # 优化点：指数退避 + 随机抖动 (Jitter)
                    wait_time = (base_delay * (2 ** i)) + (random.random() * 0.1)
                    time.sleep(wait_time)
                    continue
                raise e
            except Exception as e:
                try:
                    self._get_conn().rollback()
                except:
                    pass
                raise e
        
        if last_error:
            raise last_error
        # 注意：这里不 close，由连接池/线程生命周期管理

    def _daily_maintenance(self, cursor):
        """执行日常维护任务（如自检、清理）"""
        try:
            # 记录上次自检日期
            today = time.strftime("%Y-%m-%d")
            cursor.execute("CREATE TABLE IF NOT EXISTS sys_maintenance (task_name TEXT PRIMARY KEY, last_run TEXT)")
            
            cursor.execute("SELECT last_run FROM sys_maintenance WHERE task_name = 'integrity_check'")
            row = cursor.fetchone()
            if not row or row['last_run'] != today:
                print(f"[{today}] 执行数据库完整性检查与统计信息更新...")
                # 1. 完整性检查
                cursor.execute("PRAGMA integrity_check")
                res = cursor.fetchone()
                
                # 2. 统计信息更新 (优化查询计划)
                cursor.execute("ANALYZE")
                
                if res and res[0] == "ok":
                    cursor.execute("INSERT OR REPLACE INTO sys_maintenance (task_name, last_run) VALUES ('integrity_check', ?)", (today,))
                else:
                    print(f"警告：数据库完整性检查未通过！{res}")
        except Exception as e:
            print(f"维护任务异常: {e}")

    def _init_db(self):
        with self.transaction("IMMEDIATE") as conn:
            cursor = conn.cursor()
            
            # 优化点：执行每日一次的数据库自检
            self._daily_maintenance(cursor)

            # 基础流水表 (v4.2 增强穿透式证据链)
            cursor.execute('''CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                status TEXT,
                amount DECIMAL(10, 2),
                currency TEXT DEFAULT 'CNY',
                vendor TEXT,
                category TEXT,
                trace_id TEXT UNIQUE, 
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                file_path TEXT,
                file_hash TEXT UNIQUE,
                inference_log TEXT -- 存储推理路径 (JSON)
            )''')

            # 优化点：多维核算标签表 (F3.2.3)
            cursor.execute('''CREATE TABLE IF NOT EXISTS transaction_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_id INTEGER,
                tag_key TEXT,
                tag_value TEXT,
                FOREIGN KEY(transaction_id) REFERENCES transactions(id)
            )''')
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tag_kv ON transaction_tags(tag_key, tag_value)")

            # 优化点：增加常用查询字段索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trans_status ON transactions(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trans_vendor ON transactions(vendor)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trans_trace ON transactions(trace_id)")

            # 待匹配条目表
            cursor.execute('''CREATE TABLE IF NOT EXISTS pending_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                amount DECIMAL(10, 2),
                vendor_keyword TEXT,
                status TEXT DEFAULT 'PENDING',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )''')
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_pending_status ON pending_entries(status)")

            # 知识库表（增加审计反馈字段）
            cursor.execute('''CREATE TABLE IF NOT EXISTS knowledge_base (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_name TEXT UNIQUE,
                category_mapping TEXT,
                hit_count INTEGER DEFAULT 0,
                reject_count INTEGER DEFAULT 0, -- 新增：记录审计驳回次数
                audit_level TEXT DEFAULT 'GRAY',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )''')

            # 优化点：构建穿透式全路径视图 (F3.2.4)
            cursor.execute('''CREATE VIEW IF NOT EXISTS v_audit_trail AS
                SELECT 
                    t.id as trans_id, t.created_at, t.vendor, t.amount, t.category, t.status,
                    t.inference_log,
                    GROUP_CONCAT(tg.tag_key || ':' || tg.tag_value, '|') as tags
                FROM transactions t
                LEFT JOIN transaction_tags tg ON t.id = tg.transaction_id
                GROUP BY t.id
            ''')
            
            # 创建 FTS5 虚拟表用于语义模糊匹配
            try:
                cursor.execute("CREATE VIRTUAL TABLE IF NOT EXISTS kb_fts USING fts5(entity_name, content='knowledge_base', content_rowid='id')")
                # 触发器同步 FTS 索引
                cursor.execute('''CREATE TRIGGER IF NOT EXISTS kb_ai AFTER INSERT ON knowledge_base BEGIN
                                  INSERT INTO kb_fts(rowid, entity_name) VALUES (new.id, new.entity_name);
                                END;''')
            except sqlite3.OperationalError:
                # 某些旧版 SQLite 可能不支持 FTS5，优雅降级
                pass
            
            # 系统状态表
            cursor.execute('''CREATE TABLE IF NOT EXISTS sys_status (
                service_name TEXT PRIMARY KEY,
                last_heartbeat DATETIME DEFAULT CURRENT_TIMESTAMP,
                status TEXT,
                panic_msg TEXT, -- 存储异常堆栈快照
                metrics TEXT 
            )''')

            # 导出审计记录表
            cursor.execute('''CREATE TABLE IF NOT EXISTS export_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                export_id TEXT UNIQUE,
                filename TEXT,
                record_count INTEGER,
                operator TEXT,
                filters TEXT, -- 存储导出的过滤条件 (JSON)
                status TEXT, -- PENDING, COMPLETED, FAILED
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )''')
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_export_operator ON export_audit(operator)")

    def fix_orphaned_transactions(self):
        """
        清理因系统异常关闭导致的中间状态数据
        """
        try:
            with self.transaction("IMMEDIATE") as conn:
                # 如果单据处于 MATCHING 超过 1 小时，回退到 PENDING
                sql = "UPDATE transactions SET status = 'PENDING' WHERE status = 'MATCHING' AND datetime(created_at) < datetime('now', '-1 hour')"
                res = conn.execute(sql)
                return res.rowcount
        except Exception:
            return 0

    def backup_db(self, backup_path):
        """在线热备份数据库"""
        try:
            with self.transaction("DEFERRED") as conn:
                conn.execute(f"VACUUM INTO '{backup_path}'")
            return True
        except Exception as e:
            print(f"备份失败: {e}")
            return False

    def acquire_business_lock(self, service_name, owner_id):
        """抢占业务排他锁"""
        with self.transaction("IMMEDIATE") as conn:
            cursor = conn.cursor()
            # 抢占逻辑：如果锁为空或为自己持有
            cursor.execute('''
                UPDATE sys_status 
                SET lock_owner = ?, last_heartbeat = CURRENT_TIMESTAMP
                WHERE service_name = ? AND (lock_owner IS NULL OR lock_owner = ?)
            ''', (owner_id, service_name, owner_id))
            return cursor.rowcount > 0

    def add_transaction_with_tags(self, tags=None, **kwargs):
        """
        带标签原子化入库 (F3.2.3)
        """
        try:
            import json
            # 处理 inference_log 序列化
            if 'inference_log' in kwargs and isinstance(kwargs['inference_log'], dict):
                kwargs['inference_log'] = json.dumps(kwargs['inference_log'], ensure_ascii=False)

            with self.transaction("IMMEDIATE") as conn:
                # 1. 插入主表
                fields = ", ".join(kwargs.keys())
                placeholders = ", ".join(["?"] * len(kwargs))
                values = tuple(kwargs.values())
                sql = f"INSERT INTO transactions ({fields}) VALUES ({placeholders})"
                cursor = conn.execute(sql, values)
                trans_id = cursor.lastrowid

                # 2. 插入标签表
                if tags and trans_id:
                    tag_sql = "INSERT INTO transaction_tags (transaction_id, tag_key, tag_value) VALUES (?, ?, ?)"
                    for tag in tags:
                        conn.execute(tag_sql, (trans_id, tag['key'], tag['value']))
                
                return trans_id
        except sqlite3.IntegrityError:
            return None
        except Exception as e:
            print(f"入库失败: {e}")
            return None

    def add_transaction(self, **kwargs):
        fields = ", ".join(kwargs.keys())
        placeholders = ", ".join(["?"] * len(kwargs))
        values = tuple(kwargs.values())
        sql = f"INSERT INTO transactions ({fields}) VALUES ({placeholders})"
        try:
            with self.transaction("IMMEDIATE") as conn:
                cursor = conn.cursor()
                cursor.execute(sql, values)
                return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None

    def get_ledger_stats(self):
        """获取系统账目统计摘要"""
        sql = "SELECT status, COUNT(*) as count, SUM(amount) as total_amount FROM transactions GROUP BY status"
        try:
            with self.transaction("DEFERRED") as conn:
                return [dict(row) for row in conn.execute(sql).fetchall()]
        except Exception:
            return []

    def get_avg_daily_expenditure(self, days=30):
        """计算过去 N 天的平均日支出 (基于已审计数据)"""
        sql = """
            SELECT SUM(amount) / ? as avg_out
            FROM transactions 
            WHERE status = 'AUDITED' 
            AND created_at >= date('now', ?)
        """
        try:
            with self.transaction("DEFERRED") as conn:
                res = conn.execute(sql, (days, f'-{days} days')).fetchone()
                return res['avg_out'] if res and res['avg_out'] else 0
        except Exception:
            return 0

    def update_heartbeat(self, service_name, status="OK", owner_id=None, metrics=None):
        with self.transaction("IMMEDIATE") as conn:
            conn.execute('''
                INSERT OR REPLACE INTO sys_status (service_name, last_heartbeat, status, metrics)
                VALUES (?, CURRENT_TIMESTAMP, ?, ?)
            ''', (service_name, status, metrics))

    def check_health(self, service_name, timeout_seconds=60):
        """检查服务心跳是否超时"""
        sql = """
            SELECT (strftime('%s','now') - strftime('%s', last_heartbeat)) < ? as healthy
            FROM sys_status WHERE service_name = ?
        """
        try:
            with self.transaction("DEFERRED") as conn:
                res = conn.execute(sql, (timeout_seconds, service_name)).fetchone()
                return bool(res['healthy']) if res else False
        except:
            return False

    def integrity_check(self):
        """执行数据库完整性检查"""
        try:
            with self.transaction("DEFERRED") as conn:
                res = conn.execute("PRAGMA integrity_check").fetchone()
                return res[0] == "ok"
        except Exception:
            return False

    def vacuum(self):
        """整理数据库碎片，优化空间占用"""
        try:
            conn = self._get_conn()
            conn.execute("VACUUM")
            return True
        except Exception:
            return False
