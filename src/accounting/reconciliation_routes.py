from typing import List, Optional
from datetime import datetime
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel

from core.db_helper import DBHelper
from core.db_models import Transaction
from core.reconciliation_models import BankStatement, ReconciliationLog, ReconciliationStatus
from auth.middleware.auth_middleware import get_current_user, CurrentUser
from engine.reconciliation_engine import ReconciliationEngine
from infra.logger import get_logger

router = APIRouter(prefix="/reconciliation", tags=["Reconciliation"])
log = get_logger("ReconciliationAPI")

# --- Schemas ---
class BankStatementSchema(BaseModel):
    id: int
    source_type: str
    transaction_date: datetime
    amount: Decimal
    counterparty_name: Optional[str]
    description: Optional[str]
    status: str

    class Config:
        from_attributes = True

class ReconciliationStats(BaseModel):
    total_statements: int
    unreconciled: int
    matched: int
    reconciled: int

# --- API Endpoints ---

@router.post("/upload", summary="上传银行流水")
async def upload_bank_statement(
    source_type: str,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    上传并解析银行流水 (CSV/Excel)
    目前仅作为演示，直接模拟插入几条数据
    """
    # TODO: 实现真正的 CSV/Excel 解析逻辑 (pandas)
    # df = pd.read_csv(file.file)

    # 模拟数据
    mock_statements = [
        BankStatement(
            organization_id=current_user.organization_id,
            source_type=source_type,
            account_number="622202***",
            transaction_date=datetime.now(),
            amount=Decimal("100.00"),
            external_id=f"MOCK-{int(datetime.now().timestamp())}-1",
            description="模拟测试流水 1",
            status=ReconciliationStatus.UNRECONCILED
        ),
        BankStatement(
            organization_id=current_user.organization_id,
            source_type=source_type,
            account_number="622202***",
            transaction_date=datetime.now(),
            amount=Decimal("-50.00"),
            external_id=f"MOCK-{int(datetime.now().timestamp())}-2",
            description="模拟测试流水 2",
            status=ReconciliationStatus.UNRECONCILED
        )
    ]

    db = DBHelper()
    try:
        with db.transaction() as session:
            for stmt in mock_statements:
                session.add(stmt)
        return {"message": f"Successfully uploaded {len(mock_statements)} statements"}
    except Exception as e:
        log.error(f"Upload failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/run", summary="执行自动对账")
async def run_reconciliation(
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    触发自动对账任务 (异步执行)
    """
    engine = ReconciliationEngine()

    # 在后台运行，不阻塞 API
    background_tasks.add_task(engine.run, current_user.organization_id)

    return {"message": "Reconciliation task started in background"}

@router.get("/stats", response_model=ReconciliationStats)
async def get_reconciliation_stats(
    current_user: CurrentUser = Depends(get_current_user)
):
    """获取对账统计概览"""
    db = DBHelper()
    with db.transaction() as session:
        query = session.query(BankStatement).filter(
            BankStatement.organization_id == current_user.organization_id
        )

        total = query.count()
        unreconciled = query.filter(BankStatement.status == ReconciliationStatus.UNRECONCILED).count()
        matched = query.filter(BankStatement.status == ReconciliationStatus.MATCHED).count()
        reconciled = query.filter(BankStatement.status == ReconciliationStatus.RECONCILED).count()

        return {
            "total_statements": total,
            "unreconciled": unreconciled,
            "matched": matched,
            "reconciled": reconciled
        }

@router.get("/statements", response_model=List[BankStatementSchema])
async def list_statements(
    status: Optional[str] = None,
    page: int = 1,
    size: int = 20,
    current_user: CurrentUser = Depends(get_current_user)
):
    """查询银行流水列表"""
    db = DBHelper()
    with db.transaction() as session:
        query = session.query(BankStatement).filter(
            BankStatement.organization_id == current_user.organization_id
        )

        if status:
            query = query.filter(BankStatement.status == status)

        items = query.order_by(BankStatement.transaction_date.desc()).offset((page - 1) * size).limit(size).all()
        return items

@router.post("/confirm/{log_id}")
async def confirm_match(
    log_id: int,
    current_user: CurrentUser = Depends(get_current_user)
):
    """人工确认匹配结果"""
    db = DBHelper()
    with db.transaction() as session:
        recon_log = session.query(ReconciliationLog).filter(
            ReconciliationLog.id == log_id,
            ReconciliationLog.organization_id == current_user.organization_id
        ).first()

        if not recon_log:
            raise HTTPException(status_code=404, detail="Match record not found")

        recon_log.is_confirmed = True
        recon_log.confirmed_by = current_user.user_id
        recon_log.confirmed_at = datetime.now()

        # 更新流水状态为 RECONCILED
        stmt = session.query(BankStatement).get(recon_log.statement_id)
        stmt.status = ReconciliationStatus.RECONCILED

        return {"message": "Match confirmed"}
