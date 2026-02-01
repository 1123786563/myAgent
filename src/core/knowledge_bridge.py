import yaml
import shutil
import os
import hashlib
import re
import difflib
from core.db_helper import DBHelper
from core.db_models import KnowledgeBase, Transaction
from infra.logger import get_logger
from sqlalchemy import func, text, desc

log = get_logger("KnowledgeBridge")

from typing import Dict, Any


class DTPResponse:
    """
    [Suggestion 1] 决策传输协议 (Decision Transfer Protocol)
    [Optimization 2] 增加合同条款级提取支持
    """

    def __init__(self, raw_data: Dict[str, Any]):
        self.entity = raw_data.get("entity")
        self.category = raw_data.get("category")
        self.confidence = raw_data.get("confidence", 0.0)
        self.reasoning = raw_data.get("reasoning", "")
        self.is_tax_related = raw_data.get("is_tax_related", False)
        self.payment_milestones = raw_data.get("payment_milestones", [])
        self.contract_terms = raw_data.get("contract_terms", {})


class KnowledgeBridge:
    def __init__(self, rules_path=None):
        from core.config_manager import ConfigManager

        self.rules_path = rules_path or ConfigManager.get("path.rules")
        self.db = DBHelper()

    def handle_manus_decision(self, decision: Dict[str, Any]):
        """
        [Suggestion 1] 处理 OpenManus 的决策并尝试固化
        [Optimization Round 2] 支持多实体证据链学习 (Evidence-Link Learning)
        """
        dtp = DTPResponse(decision)

        # 1. 逻辑自检：基础平衡校验与科目合法性预审 (Optimization 2)
        if dtp.category and not re.match(r"^\d{4}-\d{2}", dtp.category):
            log.error(f"DTP拦截：非法科目编码请求 -> {dtp.category}")
            return False

        if dtp.is_tax_related and dtp.confidence > 0.9:
            log.info(f"DTP: 进行税务逻辑预审 -> {dtp.entity}")

        if dtp.confidence > 0.85:
            log.info(f"DTP: 接收到高置信度决策 ({dtp.confidence}) -> {dtp.entity}")
            
            # [Optimization Round 2] 处理多实体证据
            entities = dtp.entity if isinstance(dtp.entity, list) else [dtp.entity]
            for ent in entities:
                if ent:
                    self.learn_new_rule(ent, dtp.category, source="OPENMANUS")
            return True
        else:
            log.warning(f"DTP: 决策置信度过低 ({dtp.confidence})，转入人工复核。")
            return False

    def record_rule_hit(self, keyword):
        """
        [Suggestion 5] 记录规则命中，并执行“灰度晋升”逻辑
        连续命中 3 次且零驳回则转正为 STABLE (F3.4.2)
        """
        try:
            with self.db.transaction() as session:
                # 1. 累加命中次数与连续成功数
                record = session.query(KnowledgeBase).filter_by(entity_name=keyword).first()
                if not record:
                    return False
                
                record.hit_count = (record.hit_count or 0) + 1
                record.consecutive_success = (record.consecutive_success or 0) + 1
                record.updated_at = func.now()

                # 2. 检查灰度转正阈值
                if (
                    record.audit_status == "GRAY"
                    and record.consecutive_success >= 3
                    and record.reject_count == 0
                ):
                    log.info(
                        f"灰度规则 {keyword} 通过‘面试’(3次成功)，正在晋升为 STABLE..."
                    )
                    # 先在 DB 标记
                    record.audit_status = 'STABLE'
                    # 同步 YAML
                    self._sync_to_yaml(keyword, record.category_mapping)
                    return True
        except Exception as e:
            log.error(f"规则命中记录失败: {e}")
        return False

    def record_rule_rejection(self, keyword):
        """
        记录审计驳回，若驳回次数过多则废弃该规则 (F3.4.2)
        """
        try:
            with self.db.transaction() as session:
                record = session.query(KnowledgeBase).filter_by(entity_name=keyword).first()
                if not record: return False
                
                record.reject_count = (record.reject_count or 0) + 1
                record.consecutive_success = 0
                record.updated_at = func.now()

                # 更新评分
                self._recalculate_quality_score_obj(record)

                if record.audit_status == "GRAY" and record.reject_count >= 2:
                    log.error(
                        f"规则 {keyword} 驳回次数过多 ({record.reject_count})，已被标记为 BLOCKED 废弃。"
                    )
                    record.audit_status = 'BLOCKED'
                    record.quality_score = 0.0
            return True
        except Exception as e:
            log.error(f"记录驳回失败: {e}")
        return False

    def _recalculate_quality_score_obj(self, record):
        """算法：命中率 * (1 - 衰减系数)"""
        hit = record.hit_count or 0
        rej = record.reject_count or 0
        record.quality_score = float(hit) / (hit + rej * 2 + 1)

    def promote_rule(self, keyword, category):
        """
        正式将 GRAY 规则转为 STABLE 并同步至 YAML
        """
        try:
            with self.db.transaction() as session:
                record = session.query(KnowledgeBase).filter_by(entity_name=keyword).first()
                if record:
                    record.audit_status = 'STABLE'
                    record.updated_at = func.now()

            # 同步至本地 SOP 规则库
            self._sync_to_yaml(keyword, category)
            log.info(f"规则 {keyword} 转正成功 (STABLE)！")
        except Exception as e:
            log.error(f"转正同步失败: {e}")

    def _sync_to_yaml(self, keyword, category):
        """同步数据库规则到 YAML 文件 (带原子写入保护)"""
        if not re.match(r"^\d{4}-\d{2}", category):
            log.error(f"同步拦截：非法科目编码 {category} 拒绝写入 YAML。")
            return

        from yaml_utils import safe_update_yaml

        try:
            with open(self.rules_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {"rules": []}
        except FileNotFoundError:
            data = {"rules": []}

        for rule in data["rules"]:
            if rule["keyword"] == keyword:
                rule["category"] = category
                break
        else:
            data["rules"].append({"keyword": keyword, "category": category})

        if safe_update_yaml(str(self.rules_path), data):
            log.info(f"规则库 YAML 原子更新成功: {keyword}")
        else:
            log.error(f"规则库 YAML 原子更新失败: {keyword}")

    def learn_new_rule(self, keyword, category, source="OPENMANUS"):
        """
        [Optimization 3] 事务性学习新知识，增加冲突“预温”校验 (F3.4.2)
        [Round 4] 支持 HITL 反馈回流，将用户修正写入规则库并标记为 GRAY
        """
        try:
            with self.db.transaction() as session:
                existing = session.query(KnowledgeBase).filter_by(entity_name=keyword).first()
                
                audit_status = "STABLE" if source == "MANUAL" else "GRAY"
                
                if (
                    existing
                    and existing.audit_status == "STABLE"
                    and existing.category_mapping != category
                ):
                    log.warning(
                        f"检测到新规则与稳定规则冲突: {keyword} ({existing.category_mapping} -> {category})"
                    )
                    # 标记为质疑状态，但仍维持 GRAY
                    audit_status = "GRAY"

                # UPSERT
                if existing:
                    existing.category_mapping = category
                    if existing.audit_status == 'BLOCKED':
                        existing.audit_status = 'GRAY'
                    else:
                        # 如果 manual 写入，提升到 STABLE
                        if source == "MANUAL": existing.audit_status = 'STABLE'
                    
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

            # 同步至 YAML
            if source == "MANUAL" or audit_status == "STABLE":
                self._sync_to_yaml(keyword, category)

            log.info(f"知识同步完成: {keyword} -> {category} (Status: {audit_status})")
            return True
        except Exception as e:
            log.error(f"同步失败: {e}")
            return False

    def _extract_rules_from_audited_tx(self):
        """
        [Optimization Round 1] 自动从已通过审计且具有高置信度（或 L2 修复）的交易中提取规则
        """
        log.info("执行从已审计交易提取知识...")
        try:
            with self.db.transaction() as session:
                # 查找已审计通过记录
                candidates = session.query(Transaction.vendor, Transaction.category).filter(
                    Transaction.status.in_(['AUDITED', 'COMPLETED', 'POSTED']),
                    Transaction.vendor != None
                ).distinct().limit(50).all()
            
            for cand in candidates:
                vendor = cand.vendor
                category = cand.category
                # 检查 KB
                with self.db.transaction() as session:
                    exists = session.query(KnowledgeBase).filter_by(entity_name=vendor, audit_status='STABLE').first()
                    if not exists:
                        self.learn_new_rule(vendor, category, source="AUTO_DISTILL")
                
        except Exception as e:
            log.error(f"从交易提取知识失败: {e}")

    def distill_knowledge(self):
        """
        [Optimization 4] 增强型知识蒸馏与语义去重 (F2.6)
        """
        log.info("启动增强型时效性语义蒸馏程序...")
        
        # 0. 从已审计交易中提取新规则
        self._extract_rules_from_audited_tx()

        try:
            with self.db.transaction() as session:
                # 1. 处理冲突：同名实体的不同分类
                # 这里我们利用 SQLAlchemy 查找重复项
                duplicates = session.query(KnowledgeBase.entity_name).group_by(KnowledgeBase.entity_name).having(func.count(KnowledgeBase.category_mapping) > 1).all()
                
                for dup in duplicates:
                    name = dup.entity_name
                    
                    # 检查是否有 STABLE
                    stable = session.query(KnowledgeBase).filter_by(entity_name=name, audit_status='STABLE').first()
                    if stable:
                        # 删除所有冲突的 GRAY
                        session.query(KnowledgeBase).filter(
                            KnowledgeBase.entity_name == name,
                            KnowledgeBase.audit_status == 'GRAY'
                        ).delete()
                        log.info(f"Distillation: Enforced STABLE rule for '{name}'")
                    else:
                        # 留优汰劣
                        best = session.query(KnowledgeBase).filter_by(entity_name=name).order_by(desc(KnowledgeBase.quality_score), desc(KnowledgeBase.updated_at)).first()
                        if best:
                            session.query(KnowledgeBase).filter(
                                KnowledgeBase.entity_name == name,
                                KnowledgeBase.id != best.id
                            ).delete()

                # 2. 语义聚类合并
                all_gray = session.query(KnowledgeBase).filter_by(audit_status='GRAY').all()
                to_delete = set()
                
                for i in range(len(all_gray)):
                    if all_gray[i].id in to_delete: continue
                    for j in range(i + 1, len(all_gray)):
                        if all_gray[j].id in to_delete: continue
                        
                        ratio = difflib.SequenceMatcher(None, all_gray[i].entity_name, all_gray[j].entity_name).ratio()
                        if ratio > 0.85 and all_gray[i].category_mapping == all_gray[j].category_mapping:
                            victim = all_gray[i].id if (all_gray[i].quality_score or 0) < (all_gray[j].quality_score or 0) else all_gray[j].id
                            to_delete.add(victim)

                if to_delete:
                    session.query(KnowledgeBase).filter(KnowledgeBase.id.in_(list(to_delete))).delete(synchronize_session=False)
                    log.info(f"成功清理了 {len(to_delete)} 条冗余语义规则")

            log.info("知识蒸馏完成。")
            return True
        except Exception as e:
            log.error(f"知识蒸馏失败: {e}")
            return False

    def record_match_success(self, keyword):
        try:
            with self.db.transaction() as session:
                record = session.query(KnowledgeBase).filter_by(entity_name=keyword).first()
                if record:
                    record.hit_count = (record.hit_count or 0) + 1
                    record.updated_at = func.now()
        except Exception as e:
            log.error(f"记录对账经验失败: {keyword}, {e}")

    def cleanup_stale_rules(self, min_hits=0, days_old=30):
        try:
            with self.db.transaction() as session:
                cutoff = datetime.datetime.now() - datetime.timedelta(days=days_old)
                deleted = session.query(KnowledgeBase).filter(
                    KnowledgeBase.audit_status == 'GRAY',
                    KnowledgeBase.hit_count <= min_hits,
                    KnowledgeBase.updated_at < cutoff
                ).delete()
                log.info(f"清理了 {deleted} 条过期临时规则。")
            return True
        except Exception as e:
            log.error(f"清理规则失败: {e}")
            return False
