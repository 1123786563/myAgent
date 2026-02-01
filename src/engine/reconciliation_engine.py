import json
from datetime import timedelta
from decimal import Decimal
from typing import List, Optional
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from core.db_helper import DBHelper
from core.db_models import Transaction
from core.reconciliation_models import (
    BankStatement, ReconciliationRule, ReconciliationLog,
    ReconciliationStatus, MatchMethod
)
from infra.logger import get_logger

log = get_logger("ReconciliationEngine")

class ReconciliationEngine:
    """
    财务对账引擎
    负责将外部银行流水 (BankStatement) 与内部交易 (Transaction) 进行核对
    """

    def __init__(self, db: DBHelper = None):
        self.db = db or DBHelper()

    def run(self, organization_id: int):
        """执行指定租户的对账任务"""
        log.info(f"Starting reconciliation for Org {organization_id}...")

        with self.db.transaction() as session:
            # 1. 加载所有激活的规则 (按优先级排序)
            rules = session.query(ReconciliationRule).filter(
                ReconciliationRule.organization_id == organization_id,
                ReconciliationRule.is_active == True
            ).order_by(ReconciliationRule.priority.desc()).all()

            matched_count = 0

            # 2. 依次应用规则
            for rule in rules:
                count = self._apply_rule(session, organization_id, rule)
                matched_count += count

            log.info(f"Reconciliation completed. Total matched: {matched_count}")

    def _apply_rule(self, session: Session, organization_id: int, rule: ReconciliationRule) -> int:
        """应用单条对账规则"""
        conditions = rule.conditions # JSON dict
        if isinstance(conditions, str):
            conditions = json.loads(conditions)

        # 提取条件参数
        amount_tolerance = Decimal(str(conditions.get("amount_tolerance", "0.01")))
        date_range_days = int(conditions.get("date_range_days", 3))

        # 获取未对账的流水
        statements = session.query(BankStatement).filter(
            BankStatement.organization_id == organization_id,
            BankStatement.status == ReconciliationStatus.UNRECONCILED
        ).all()

        match_count = 0

        for stmt in statements:
            # 构建查询：寻找匹配的 Transaction
            # 基本条件：未对账 + 租户匹配
            query = session.query(Transaction).filter(
                Transaction.organization_id == organization_id,
                # 假设 Transaction 也有类似 status，或者通过关联表判断
                # 这里简化处理，假设 Transaction.status 字段兼容
                # 实际项目中可能需要关联查询 ReconciliationLog 来排除已对账的
                or_(Transaction.status == None, Transaction.status != "RECONCILED")
            )

            # 1. 金额匹配 (支持容差)
            # 注意：BankStatement amount 正负方向需与 Transaction 一致
            min_amount = stmt.amount - amount_tolerance
            max_amount = stmt.amount + amount_tolerance
            query = query.filter(Transaction.amount >= min_amount, Transaction.amount <= max_amount)

            # 2. 日期匹配 (范围)
            min_date = stmt.transaction_date - timedelta(days=date_range_days)
            max_date = stmt.transaction_date + timedelta(days=date_range_days)
            query = query.filter(Transaction.created_at >= min_date, Transaction.created_at <= max_date)

            # 3. 备注/关键字匹配 (如果规则配置了)
            # match_fields = conditions.get("match_fields", [])
            # if "order_no" in match_fields and stmt.reference_code:
            #     query = query.filter(Transaction.trace_id == stmt.reference_code)

            candidates = query.all()

            # 简单策略：如果找到唯一的匹配项，则认为匹配成功
            # 复杂策略可能需要更精细的评分
            if len(candidates) == 1:
                transaction = candidates[0]
                self._create_match(session, stmt, transaction, rule, MatchMethod.AUTO_RULE)
                match_count += 1

        return match_count

    def _create_match(
        self,
        session: Session,
        stmt: BankStatement,
        trans: Transaction,
        rule: ReconciliationRule,
        method: MatchMethod
    ):
        """创建匹配记录并更新状态"""
        log.info(f"Match found: Stmt {stmt.id} <-> Trans {trans.id} via Rule '{rule.name}'")

        # 1. 创建日志
        recon_log = ReconciliationLog(
            organization_id=stmt.organization_id,
            statement_id=stmt.id,
            transaction_id=trans.id,
            match_method=method,
            score=1.0, # 规则匹配默认为 1.0
            match_reason=f"Matched by rule: {rule.name}",
            is_confirmed=rule.auto_approve # 如果规则允许自动确认
        )
        session.add(recon_log)

        # 2. 更新流水状态
        stmt.status = ReconciliationStatus.MATCHED
        if rule.auto_approve:
             stmt.status = ReconciliationStatus.RECONCILED

        # 3. 更新交易状态
        trans.status = "MATCHED"
        if rule.auto_approve:
            trans.status = "RECONCILED"

    def match_by_ai(self, organization_id: int):
        """
        TODO: AI 辅助匹配逻辑
        1. 查找所有 UNRECONCILED 流水和交易
        2. 构造 Prompt 发送给 LLM
        3. 解析返回结果并创建建议匹配 (MatchMethod.AI_SUGGESTION)
        """
        pass
