import yaml
import shutil
import os
import hashlib
import re
import difflib
from core.db_helper import DBHelper
from infra.logger import get_logger

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
        [Optimization 3] 决策传输协议 (DTP) 逻辑自检
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
            # 记录审计理由到数据库
            self.learn_new_rule(dtp.entity, dtp.category, source="OPENMANUS")
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
            with self.db.transaction("IMMEDIATE") as conn:
                # 1. 累加命中次数与连续成功数
                conn.execute(
                    """
                    UPDATE knowledge_base 
                    SET hit_count = hit_count + 1, 
                        consecutive_success = consecutive_success + 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE entity_name = ?
                """,
                    (keyword,),
                )

                # 2. 检查灰度转正阈值
                row = conn.execute(
                    """
                    SELECT category_mapping, audit_status, consecutive_success, reject_count 
                    FROM knowledge_base WHERE entity_name = ?
                """,
                    (keyword,),
                ).fetchone()

                if (
                    row
                    and row["audit_status"] == "GRAY"
                    and row["consecutive_success"] >= 3
                ):
                    if row["reject_count"] == 0:
                        log.info(
                            f"灰度规则 {keyword} 通过‘面试’(3次成功)，正在晋升为 STABLE..."
                        )
                        self.promote_rule(keyword, row["category_mapping"])
                        return True
        except Exception as e:
            log.error(f"规则命中记录失败: {e}")
        return False

    def record_rule_rejection(self, keyword):
        """
        记录审计驳回，若驳回次数过多则废弃该规则 (F3.4.2)
        """
        try:
            with self.db.transaction("IMMEDIATE") as conn:
                conn.execute(
                    """
                    UPDATE knowledge_base 
                    SET reject_count = reject_count + 1, 
                        consecutive_success = 0,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE entity_name = ?
                """,
                    (keyword,),
                )

                # 更新评分
                self._recalculate_quality_score(conn, keyword)

                row = conn.execute(
                    "SELECT reject_count, audit_status FROM knowledge_base WHERE entity_name = ?",
                    (keyword,),
                ).fetchone()
                if row and row["audit_status"] == "GRAY" and row["reject_count"] >= 2:
                    log.error(
                        f"规则 {keyword} 驳回次数过多 ({row['reject_count']})，已被标记为 BLOCKED 废弃。"
                    )
                    conn.execute(
                        "UPDATE knowledge_base SET audit_status = 'BLOCKED', quality_score = 0.0 WHERE entity_name = ?",
                        (keyword,),
                    )
            return True
        except Exception as e:
            log.error(f"记录驳回失败: {e}")
        return False

    def _recalculate_quality_score(self, conn, keyword):
        """
        算法：命中率 * (1 - 衰减系数)，并检查是否存在科目冲突
        """
        # 1. 基础评分更新
        sql = """
            UPDATE knowledge_base 
            SET quality_score = CAST(hit_count AS REAL) / (hit_count + reject_count * 2 + 1)
            WHERE entity_name = ?
        """
        conn.execute(sql, (keyword,))

        # 2. 检查冲突蒸馏 (Suggestion 1)
        conflict_sql = """
            SELECT id, quality_score FROM knowledge_base 
            WHERE entity_name = ? AND audit_status = 'GRAY'
            ORDER BY quality_score DESC
        """
        rows = conn.execute(conflict_sql, (keyword,)).fetchall()
        if len(rows) > 1:
            best_id = rows[0]["id"]
            log.info(f"检测到规则冲突: {keyword}, 正在执行蒸馏，保留 ID: {best_id}")
            conn.execute(
                "DELETE FROM knowledge_base WHERE entity_name = ? AND id != ?",
                (keyword, best_id),
            )

    def promote_rule(self, keyword, category):
        """
        正式将 GRAY 规则转为 STABLE 并同步至 YAML
        """
        try:
            with self.db.transaction("IMMEDIATE") as conn:
                conn.execute(
                    """
                    UPDATE knowledge_base 
                    SET audit_status = 'STABLE' 
                    WHERE entity_name = ?
                """,
                    (keyword,),
                )

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

        with open(self.rules_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {"rules": []}

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
        # 1. 冲突预检
        try:
            with self.db.transaction("DEFERRED") as conn:
                existing = conn.execute(
                    "SELECT category_mapping, audit_status FROM knowledge_base WHERE entity_name = ?",
                    (keyword,),
                ).fetchone()
                if (
                    existing
                    and existing["audit_status"] == "STABLE"
                    and existing["category_mapping"] != category
                ):
                    log.warning(
                        f"检测到新规则与稳定规则冲突: {keyword} ({existing['category_mapping']} -> {category})"
                    )
                    # 标记为质疑状态
                    source = "CONFLICT_CHALLENGED"
        except:
            pass

        backup_path = self.rules_path + ".bak"
        success = False

        try:
            # 备份现有规则
            if os.path.exists(self.rules_path):
                shutil.copy(self.rules_path, backup_path)

            # 更新数据库
            # 如果来源是 MANUAL，仍然先标记为 STABLE 并在数据库中生效
            # 但如果是 Round 4 的要求，我们需要将用户反馈也写入 YAML 规则列表（作为高优先级或待观察）
            
            audit_status = "STABLE" if source == "MANUAL" else "GRAY"
            if source == "CONFLICT_CHALLENGED":
                audit_status = "GRAY"  # Still gray but warned

            with self.db.transaction("IMMEDIATE") as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO knowledge_base 
                    (entity_name, category_mapping, audit_status, hit_count)
                    VALUES (?, ?, ?, 1)
                    ON CONFLICT(entity_name) DO UPDATE SET
                        category_mapping = excluded.category_mapping,
                        audit_status = CASE WHEN audit_status = 'BLOCKED' THEN 'GRAY' ELSE audit_status END,
                        hit_count = hit_count + 1,
                        updated_at = CURRENT_TIMESTAMP
                """,
                    (keyword, category, audit_status),
                )

            # 3. 同步至 YAML
            # [Round 4] 无论是 STABLE (Manual) 还是 GRAY (New Rule)，都写入 YAML 以便 accounting_agent 立即生效
            # 但 GRAY 规则在 YAML 中可能需要特殊标记，或者仅仅作为普通规则写入，依靠 DB 里的状态进行后续清理
            # 这里我们选择写入所有 MANUAL 来源的规则到 YAML，确保 accounting_agent 能加载
            
            if source == "MANUAL" or audit_status == "STABLE":
                self._sync_to_yaml(keyword, category)

            success = True
            log.info(f"知识同步完成: {keyword} -> {category} (Status: {audit_status})")

        except Exception as e:
            log.error(f"同步失败，触发回滚: {e}")
            if os.path.exists(backup_path):
                shutil.copy(backup_path, self.rules_path)
            raise e
        finally:
            if os.path.exists(backup_path):
                os.remove(backup_path)
        return success

    def _extract_rules_from_audited_tx(self):
        """
        [Optimization Round 1] 自动从已通过审计且具有高置信度（或 L2 修复）的交易中提取规则
        """
        log.info("执行从已审计交易提取知识...")
        try:
            # 查找已审计通过，且由 L2 推理或高置信度 L1 产生的记录，且目前在 KB 中还不是 STABLE 的
            sql = """
                SELECT DISTINCT vendor, category 
                FROM transactions t
                WHERE t.status IN ('AUDITED', 'COMPLETED', 'POSTED')
                AND t.vendor IS NOT NULL
                AND NOT EXISTS (
                    SELECT 1 FROM knowledge_base k 
                    WHERE k.entity_name = t.vendor AND k.audit_status = 'STABLE'
                )
                LIMIT 50
            """
            with self.db.transaction("DEFERRED") as conn:
                candidates = conn.execute(sql).fetchall()
            
            for cand in candidates:
                vendor = cand["vendor"]
                category = cand["category"]
                # 再次调用 learn_new_rule，它会处理 GRAY 逻辑
                self.learn_new_rule(vendor, category, source="AUTO_DISTILL")
                
        except Exception as e:
            log.error(f"从交易提取知识失败: {e}")

    def distill_knowledge(self):
        """
        [Optimization 4] 增强型知识蒸馏与语义去重 (F2.6)
        [Optimization Round 1] 增加从已审计交易中自动学习的能力
        Safety: Protects STABLE (Manual) rules from being deleted.
        """
        log.info("启动增强型时效性语义蒸馏程序...")
        
        # 0. 从已审计交易中提取新规则 (New Logic)
        self._extract_rules_from_audited_tx()

        try:
            with self.db.transaction("IMMEDIATE") as conn:
                # ... (rest of the existing logic)
                # 1. 常规冲突裁决：利用 v_knowledge_conflicts 视图
                # This view only selects entities with >1 distinct categories in GRAY status.
                conflicts = conn.execute(
                    "SELECT entity_name FROM v_knowledge_conflicts"
                ).fetchall()
                for c in conflicts:
                    name = c["entity_name"]

                    # [Safety Fix] Check if a STABLE rule exists for this entity
                    stable_row = conn.execute(
                        "SELECT id, category_mapping FROM knowledge_base WHERE entity_name = ? AND audit_status = 'STABLE'",
                        (name,),
                    ).fetchone()

                    if stable_row:
                        # If STABLE exists, purge all GRAY rules that conflict (or all GRAYs to be clean)
                        # We trust the STABLE rule as the ground truth.
                        conn.execute(
                            "DELETE FROM knowledge_base WHERE entity_name = ? AND audit_status = 'GRAY'",
                            (name,),
                        )
                        log.info(
                            f"Distillation: Enforced STABLE rule for '{name}', purged conflicting GRAY rules."
                        )
                    else:
                        # No STABLE rule, use temporal priority among GRAY rules
                        # Strategy: Keep the one with highest score, tie-break with recency
                        sql_best = """
                            SELECT id FROM knowledge_base 
                            WHERE entity_name = ? 
                            ORDER BY quality_score DESC, updated_at DESC
                            LIMIT 1
                        """
                        best_row = conn.execute(sql_best, (name,)).fetchone()
                        if best_row:
                            conn.execute(
                                "DELETE FROM knowledge_base WHERE entity_name = ? AND id != ?",
                                (name, best_row["id"]),
                            )

                # 2. [Optimization 1] 语义聚类合并：相同映射但关键词相似
                # Only operate on GRAY rules to avoid messing up manual configs
                all_gray = conn.execute(
                    "SELECT id, entity_name, category_mapping, quality_score FROM knowledge_base WHERE audit_status = 'GRAY'"
                ).fetchall()
                to_delete = set()

                for i in range(len(all_gray)):
                    if all_gray[i]["id"] in to_delete:
                        continue
                    for j in range(i + 1, len(all_gray)):
                        if all_gray[j]["id"] in to_delete:
                            continue

                        # [Optimization 4] 使用 SequenceMatcher 替代简单的 Jaccard 集合相似度
                        # 因为 'Apple Inc' 和 'Apple Corp' 顺序敏感
                        ratio = difflib.SequenceMatcher(
                            None, all_gray[i]["entity_name"], all_gray[j]["entity_name"]
                        ).ratio()

                        if (
                            ratio > 0.85
                            and all_gray[i]["category_mapping"]
                            == all_gray[j]["category_mapping"]
                        ):
                            # 合并：保留评分高的
                            victim = (
                                all_gray[i]["id"]
                                if all_gray[i]["quality_score"]
                                < all_gray[j]["quality_score"]
                                else all_gray[j]["id"]
                            )
                            to_delete.add(victim)
                            log.info(
                                f"语义合并: [{all_gray[i]['entity_name']}] <-> [{all_gray[j]['entity_name']}] (Ratio:{ratio:.2f})"
                            )

                if to_delete:
                    conn.execute(
                        f"DELETE FROM knowledge_base WHERE id IN ({','.join(map(str, to_delete))})"
                    )
                    log.info(f"成功清理了 {len(to_delete)} 条冗余语义规则")

            log.info("知识蒸馏完成。")
            return True
        except Exception as e:
            log.error(f"知识蒸馏失败: {e}")
            return False

    def record_match_success(self, keyword):
        try:
            with self.db.transaction("IMMEDIATE") as conn:
                conn.execute(
                    """
                    UPDATE knowledge_base 
                    SET hit_count = hit_count + 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE entity_name = ?
                """,
                    (keyword,),
                )
        except Exception as e:
            log.error(f"记录对账经验失败: {keyword}, {e}")

    def cleanup_stale_rules(self, min_hits=0, days_old=30):
        try:
            with self.db.transaction("IMMEDIATE") as conn:
                sql = """
                    DELETE FROM knowledge_base 
                    WHERE audit_status = 'GRAY' 
                    AND hit_count <= ? 
                    AND updated_at < date('now', ?)
                """
                cursor = conn.execute(sql, (min_hits, f"-{days_old} days"))
                log.info(f"清理了 {cursor.rowcount} 条过期临时规则。")
            return True
        except Exception as e:
            log.error(f"清理规则失败: {e}")
            return False
