import yaml
import shutil
import os
import hashlib
from db_helper import DBHelper
from logger import get_logger

log = get_logger("KnowledgeBridge")

class KnowledgeBridge:
    def __init__(self, rules_path=None):
        from config_manager import ConfigManager
        self.rules_path = rules_path or ConfigManager.get("path.rules")
        self.db = DBHelper()

    def record_rule_hit(self, keyword):
        """
        记录规则命中，并在通过 3 次审计后自动转正
        """
        try:
            with self.db.transaction("IMMEDIATE") as conn:
                # 1. 累加命中次数
                conn.execute('''
                    UPDATE knowledge_base 
                    SET hit_count = hit_count + 1, updated_at = CURRENT_TIMESTAMP
                    WHERE entity_name = ?
                ''', (keyword,))
                
                # 2. 检查是否达到转正阈值 (例如 3 次)
                row = conn.execute('''
                    SELECT category_mapping, source, hit_count, reject_count, audit_level 
                    FROM knowledge_base WHERE entity_name = ?
                ''', (keyword,)).fetchone()
                
                if row and row['audit_level'] == 'GRAY' and row['hit_count'] >= 3:
                    # 质量检查：驳回数必须为 0 才能自动转正
                    if row['reject_count'] == 0:
                        log.info(f"规则 {keyword} 已通过 3 次审计且零驳回，准备自动转正...")
                        self.promote_rule(keyword, row['category_mapping'])
                        return True
                    else:
                        log.warning(f"规则 {keyword} 虽然命中次数达标，但存在 {row['reject_count']} 次驳回，保持灰度。")
        except Exception as e:
            log.error(f"记录命中失败: {e}")
        return False

    def record_rule_rejection(self, keyword):
        """
        记录审计驳回，若驳回次数过多则废弃该规则 (F3.4.2)
        """
        try:
            with self.db.transaction("IMMEDIATE") as conn:
                conn.execute('''
                    UPDATE knowledge_base 
                    SET reject_count = reject_count + 1, updated_at = CURRENT_TIMESTAMP
                    WHERE entity_name = ?
                ''', (keyword,))
                
                row = conn.execute('SELECT reject_count, audit_level FROM knowledge_base WHERE entity_name = ?', (keyword,)).fetchone()
                if row and row['audit_level'] == 'GRAY' and row['reject_count'] >= 2:
                    log.error(f"规则 {keyword} 驳回次数过多 ({row['reject_count']})，已被标记为 FAILED 废弃。")
                    conn.execute("UPDATE knowledge_base SET audit_level = 'FAILED' WHERE entity_name = ?", (keyword,))
            return True
        except Exception as e:
            log.error(f"记录驳回失败: {e}")
        return False

    def promote_rule(self, keyword, category):
        """
        正式将 GRAY 规则转为 VERIFIED 并同步至 YAML
        """
        try:
            with self.db.transaction("IMMEDIATE") as conn:
                conn.execute('''
                    UPDATE knowledge_base 
                    SET audit_level = 'VERIFIED' 
                    WHERE entity_name = ?
                ''', (keyword,))
            
            # 同步至本地 SOP 规则库
            self._sync_to_yaml(keyword, category)
            log.info(f"规则 {keyword} 转正成功！")
        except Exception as e:
            log.error(f"转正同步失败: {e}")

    def _sync_to_yaml(self, keyword, category):
        """同步数据库规则到 YAML 文件 (带格式校验)"""
        # 安全校验：确保科目编码合法 (L1)
        if not re.match(r'^\d{4}-\d{2}', category):
            log.error(f"同步拦截：非法科目编码 {category} 拒绝写入 YAML。")
            return

        with open(self.rules_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {"rules": []}
        
        for rule in data['rules']:
            if rule['keyword'] == keyword:
                rule['category'] = category
                break
        else:
            data['rules'].append({"keyword": keyword, "category": category})

        with open(self.rules_path, 'w', encoding='utf-8') as f:
            yaml.safe_dump(data, f, allow_unicode=True)

    def learn_new_rule(self, keyword, category, source="OPENMANUS"):
        """
        事务性学习新知识，增加写后读校验机制
        """
        backup_path = self.rules_path + ".bak"
        success = False
        
        try:
            # 1. 备份现有规则
            if os.path.exists(self.rules_path):
                shutil.copy(self.rules_path, backup_path)

            # 2. 更新数据库
            audit_status = 'VERIFIED' if source == 'MANUAL' else 'GRAY'
            with self.db.transaction("IMMEDIATE") as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO knowledge_base 
                    (entity_name, category_mapping, source, audit_level, hit_count)
                    VALUES (?, ?, ?, ?, (SELECT IFNULL(hit_count,0) FROM knowledge_base WHERE entity_name=?)+1)
                ''', (keyword, category, source, audit_status, keyword))

            # 3. 更新 YAML (仅限 MANUAL 手动转正)
            if audit_status == 'VERIFIED':
                with open(self.rules_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {"rules": []}
                
                # 简单防重
                for rule in data['rules']:
                    if rule['keyword'] == keyword:
                        rule['category'] = category
                        break
                else:
                    data['rules'].append({"keyword": keyword, "category": category})

                with open(self.rules_path, 'w', encoding='utf-8') as f:
                    yaml.safe_dump(data, f, allow_unicode=True)
                
                # 优化点：写后读校验机制
                with open(self.rules_path, 'r', encoding='utf-8') as f:
                    check_data = yaml.safe_load(f)
                    if not any(r['keyword'] == keyword for r in check_data.get('rules', [])):
                        raise IOError("YAML 写入校验失败！")
            
            success = True
            log.info(f"知识同步完成: {keyword} -> {category}")

        except Exception as e:
            log.error(f"同步失败，触发回滚: {e}")
            if os.path.exists(backup_path):
                shutil.copy(backup_path, self.rules_path)
            raise e
        finally:
            if os.path.exists(backup_path):
                os.remove(backup_path)
        return success

    def cleanup_stale_rules(self, min_hits=0, days_old=30):
        """
        优化点：自动清理长期未命中且低置信度的临时规则
        """
        try:
            with self.db.transaction("IMMEDIATE") as conn:
                # 删除 30 天前创建且命中次数为 0 的 GRAY 规则
                sql = """
                    DELETE FROM knowledge_base 
                    WHERE audit_level = 'GRAY' 
                    AND hit_count <= ? 
                    AND snap_time < date('now', ?)
                """
                cursor = conn.execute(sql, (min_hits, f'-{days_old} days'))
                log.info(f"清理了 {cursor.rowcount} 条过期临时规则。")
            return True
        except Exception as e:
            log.error(f"清理规则失败: {e}")
            return False
