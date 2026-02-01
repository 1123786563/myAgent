import os
import shutil
import re
import yaml
from infra.logger import get_logger
from utils.yaml_utils import safe_update_yaml

log = get_logger("KnowledgeBridge")

class KnowledgeUpdate:
    def __init__(self, db, rules_path):
        self.db = db
        self.rules_path = rules_path

    def learn_new_rule(self, keyword, category, source="OPENMANUS"):
        try:
            with self.db.transaction("DEFERRED") as conn:
                existing = conn.execute("SELECT category_mapping, audit_status FROM knowledge_base WHERE entity_name = ?", (keyword,)).fetchone()
                if existing and existing["audit_status"] == "STABLE" and existing["category_mapping"] != category:
                    source = "CONFLICT_CHALLENGED"
        except: pass

        backup_path = self.rules_path + ".bak"
        try:
            if os.path.exists(self.rules_path): shutil.copy(self.rules_path, backup_path)
            audit_status = "STABLE" if source == "MANUAL" else "GRAY"
            with self.db.transaction("IMMEDIATE") as conn:
                conn.execute("INSERT INTO knowledge_base (entity_name, category_mapping, audit_status, hit_count) VALUES (?, ?, ?, 1) ON CONFLICT(entity_name) DO UPDATE SET category_mapping = excluded.category_mapping, audit_status = CASE WHEN audit_status = 'BLOCKED' THEN 'GRAY' ELSE audit_status END, hit_count = hit_count + 1, updated_at = CURRENT_TIMESTAMP", (keyword, category, audit_status))
            if source == "MANUAL" or audit_status == "STABLE": self._sync_to_yaml(keyword, category)
            return True
        except Exception as e:
            if os.path.exists(backup_path): shutil.copy(backup_path, self.rules_path)
            raise e
        finally:
            if os.path.exists(backup_path): os.remove(backup_path)

    def _sync_to_yaml(self, keyword, category):
        if not re.match(r"^\d{4}-\d{2}", category): return
        with open(self.rules_path, "r", encoding="utf-8") as f: data = yaml.safe_load(f) or {"rules": []}
        for rule in data["rules"]:
            if rule["keyword"] == keyword:
                rule["category"] = category
                break
        else: data["rules"].append({"keyword": keyword, "category": category})
        safe_update_yaml(str(self.rules_path), data)

    def promote_rule(self, keyword, category):
        try:
            with self.db.transaction("IMMEDIATE") as conn:
                conn.execute("UPDATE knowledge_base SET audit_status = 'STABLE' WHERE entity_name = ?", (keyword,))
            self._sync_to_yaml(keyword, category)
            return True
        except: return False
