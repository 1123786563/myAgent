"""
会计科目与凭证管理路由
Accounting Routes - Chart of Accounts, Vouchers
"""

from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
from decimal import Decimal
from auth.dependencies import require_permission
from auth.middleware.auth_middleware import CurrentUser
from accounting.accounting_service import get_accounting_service
from core.accounting_models import AccountType, BalanceDirection, AccountCategory
from infra.logger import get_logger

log = get_logger("AccountingRoutes")
router = APIRouter(prefix="/accounting", tags=["会计"])


# ==================== Schemas ====================

class AccountCreateRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    account_type: str  # ASSET, LIABILITY, EQUITY, REVENUE, EXPENSE
    balance_direction: str  # DEBIT, CREDIT
    parent_code: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None


class AccountResponse(BaseModel):
    id: int
    code: str
    name: str
    full_name: Optional[str]
    account_type: str
    balance_direction: str
    level: int
    is_leaf: bool
    is_system: bool

    class Config:
        from_attributes = True


class VoucherItemRequest(BaseModel):
    account_code: str
    direction: str  # DEBIT, CREDIT
    amount: float
    summary: Optional[str] = None
    customer: Optional[str] = None
    supplier: Optional[str] = None
    project: Optional[str] = None
    department: Optional[str] = None


class VoucherCreateRequest(BaseModel):
    voucher_date: datetime
    items: List[VoucherItemRequest]
    summary: Optional[str] = None
    voucher_type: str = "记"
    transaction_id: Optional[int] = None


class VoucherResponse(BaseModel):
    id: int
    voucher_type: str
    voucher_number: int
    voucher_date: datetime
    year: int
    month: int
    summary: Optional[str]
    status: str
    item_count: int
    total_amount: float

    class Config:
        from_attributes = True


class TrialBalanceRow(BaseModel):
    account_code: str
    account_name: str
    opening_debit: float
    opening_credit: float
    period_debit: float
    period_credit: float
    closing_debit: float
    closing_credit: float
    is_balanced: Optional[bool] = None


# ==================== 科目管理 ====================

@router.post("/accounts/init-standard", status_code=status.HTTP_201_CREATED)
async def init_standard_accounts(
    current_user: CurrentUser = Depends(require_permission("system_config:manage"))
):
    """
    初始化标准科目表

    - 创建中国企业会计准则标准科目
    - 仅管理员可操作
    """
    service = get_accounting_service()
    count = service.init_standard_accounts(
        organization_id=current_user.organization_id,
        user_id=current_user.user_id
    )
    return {"message": f"成功初始化 {count} 个标准科目", "count": count}


@router.get("/accounts", response_model=List[AccountResponse])
async def list_accounts(
    current_user: CurrentUser = Depends(require_permission("transactions:read"))
):
    """获取科目列表 (平铺)"""
    from core.db_helper import DBHelper
    from core.accounting_models import Account

    db = DBHelper()
    with db.transaction() as session:
        accounts = session.query(Account).filter_by(
            organization_id=current_user.organization_id,
            is_active=True
        ).order_by(Account.code).all()

        return [AccountResponse(
            id=acc.id,
            code=acc.code,
            name=acc.name,
            full_name=acc.full_name,
            account_type=acc.account_type.value,
            balance_direction=acc.balance_direction.value,
            level=acc.level,
            is_leaf=acc.is_leaf,
            is_system=acc.is_system
        ) for acc in accounts]


@router.get("/accounts/tree")
async def get_account_tree(
    current_user: CurrentUser = Depends(require_permission("transactions:read"))
):
    """获取科目树形结构"""
    service = get_accounting_service()
    return service.get_account_tree(current_user.organization_id)


@router.post("/accounts", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account(
    request_data: AccountCreateRequest,
    current_user: CurrentUser = Depends(require_permission("knowledge_base:manage"))
):
    """创建科目"""
    service = get_accounting_service()

    try:
        account_type = AccountType(request_data.account_type)
        balance_direction = BalanceDirection(request_data.balance_direction)
        category = AccountCategory(request_data.category) if request_data.category else None
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    account, error = service.create_account(
        organization_id=current_user.organization_id,
        code=request_data.code,
        name=request_data.name,
        account_type=account_type,
        balance_direction=balance_direction,
        parent_code=request_data.parent_code,
        category=category,
        description=request_data.description,
        user_id=current_user.user_id
    )

    if error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

    return AccountResponse(
        id=account.id,
        code=account.code,
        name=account.name,
        full_name=account.full_name,
        account_type=account.account_type.value,
        balance_direction=account.balance_direction.value,
        level=account.level,
        is_leaf=account.is_leaf,
        is_system=account.is_system
    )


# ==================== 凭证管理 ====================

@router.post("/vouchers", response_model=VoucherResponse, status_code=status.HTTP_201_CREATED)
async def create_voucher(
    request_data: VoucherCreateRequest,
    current_user: CurrentUser = Depends(require_permission("transactions:create"))
):
    """
    创建会计凭证

    - 自动验证借贷平衡
    - 验证科目是否存在且为末级科目
    """
    service = get_accounting_service()

    items = [item.model_dump() for item in request_data.items]

    voucher, error = service.create_voucher(
        organization_id=current_user.organization_id,
        voucher_date=request_data.voucher_date,
        items=items,
        summary=request_data.summary,
        voucher_type=request_data.voucher_type,
        transaction_id=request_data.transaction_id,
        user_id=current_user.user_id
    )

    if error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

    total_amount = sum(float(item.amount) for item in voucher.items if item.direction.value == "DEBIT")

    return VoucherResponse(
        id=voucher.id,
        voucher_type=voucher.voucher_type,
        voucher_number=voucher.voucher_number,
        voucher_date=voucher.voucher_date,
        year=voucher.year,
        month=voucher.month,
        summary=voucher.summary,
        status=voucher.status,
        item_count=len(voucher.items),
        total_amount=total_amount
    )


@router.post("/vouchers/{voucher_id}/post")
async def post_voucher(
    voucher_id: int,
    current_user: CurrentUser = Depends(require_permission("transactions:approve"))
):
    """
    过账凭证

    - 更新科目余额
    - 需要审批权限
    """
    service = get_accounting_service()

    success, error = service.post_voucher(
        voucher_id=voucher_id,
        organization_id=current_user.organization_id,
        user_id=current_user.user_id
    )

    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

    return {"message": "凭证过账成功"}


@router.get("/vouchers")
async def list_vouchers(
    year: Optional[int] = None,
    month: Optional[int] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: CurrentUser = Depends(require_permission("transactions:read"))
):
    """获取凭证列表"""
    from core.db_helper import DBHelper
    from core.accounting_models import Voucher

    db = DBHelper()
    with db.transaction() as session:
        query = session.query(Voucher).filter_by(
            organization_id=current_user.organization_id
        )

        if year:
            query = query.filter(Voucher.year == year)
        if month:
            query = query.filter(Voucher.month == month)
        if status:
            query = query.filter(Voucher.status == status)

        total = query.count()
        offset = (page - 1) * page_size
        vouchers = query.order_by(Voucher.voucher_date.desc()).offset(offset).limit(page_size).all()

        items = []
        for v in vouchers:
            total_amount = sum(float(item.amount) for item in v.items if item.direction.value == "DEBIT")
            items.append({
                "id": v.id,
                "voucher_type": v.voucher_type,
                "voucher_number": v.voucher_number,
                "voucher_date": v.voucher_date.isoformat(),
                "year": v.year,
                "month": v.month,
                "summary": v.summary,
                "status": v.status,
                "item_count": len(v.items),
                "total_amount": total_amount
            })

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": (total + page_size - 1) // page_size
        }


# ==================== 报表 ====================

@router.get("/reports/trial-balance", response_model=List[TrialBalanceRow])
async def get_trial_balance(
    year: int,
    month: int,
    current_user: CurrentUser = Depends(require_permission("reports:read"))
):
    """
    获取试算平衡表

    - 显示期初、本期发生、期末余额
    - 验证借贷是否平衡
    """
    service = get_accounting_service()
    return service.get_trial_balance(
        organization_id=current_user.organization_id,
        year=year,
        month=month
    )
