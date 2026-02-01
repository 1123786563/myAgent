import os
import shutil
import re
import yaml
from infra.logger import get_logger
from utils.yaml_utils import safe_update_yaml
from core.db_models import KnowledgeBase
from sqlalchemy import func

log = get_logger("KnowledgeBridge")

class KnowledgeUpdate:
    def __init__(self, db, rules_path):
        self.db = db
        self.rules_path = rules_path

    def learn_new_rule(self, keyword, category, source="OPENMANUS"):
        try:
            with self.db.transaction() as session:
                existing = session.query(KnowledgeBase).filter_by(entity_name=keyword).first()
                if existing and existing.audit_status == "STABLE" and existing.category_mapping != category:
                    source = "CONFLICT_CHALLENGED"
        except: pass

        backup_path = self.rules_path + ".bak"
        try:
            if os.path.exists(self.rules_path): shutil.copy(self.rules_path, backup_path)
            audit_status = "STABLE" if source == "MANUAL" else "GRAY"
            
            with self.db.transaction() as session:
                existing = session.query(KnowledgeBase).filter_by(entity_name=keyword).first()
                if existing:
                    existing.category_mapping = category
                    if existing.audit_status == 'BLOCKED':
                        existing.audit_status = 'GRAY'
                    elif source == "MANUAL":
                        existing.audit_status = 'STABLE'
                    existing.hit_count = (existing.hit_count or 0) + 1
                    existing.updated_at = func.now()
                else:
                    new_kb = KnowledgeBase(
                        entity_name=keyword,
                        category_mapping=category,
                        audit_status=audit_status,
                        hit_count=1
                    )
                    session.add(new_kb)

            if source == "MANUAL" or audit_status == "STABLE": self._sync_to_yaml(keyword, category)
            return True
        except Exception as e:
            if os.path.exists(backup_path): shutil.copy(backup_path, self.rules_path)
            raise e
        finally:
            if os.path.exists(backup_path): os.remove(backup_path)

    def _sync_to_yaml(self, keyword, category):
        if not re.match(r"^\d{4}-\d{2}", category): return
        try:
            with open(self.rules_path, "r", encoding="utf-8") as f: data = yaml.safe_load(f) or {"rules": []}
        except FileNotFoundError:
            data = {"rules": []}
            
        for rule in data["rules"]:
            if rule["keyword"] == keyword:
                rule["category"] = category
                break
        else: data["rules"].append({"keyword": keyword, "category": category})
        safe_update_yaml(str(self.rules_path), data)

    def promote_rule(self, keyword, category):
        try:
            with self.db.transaction() as session:
                record = session.query(KnowledgeBase).filter_by(entity_name=keyword).first()
                if record:
                    record.audit_status = 'STABLE'
                    record.updated_at = func.now()
            self._sync_to_yaml(keyword, category)
            return True
        except: return False
