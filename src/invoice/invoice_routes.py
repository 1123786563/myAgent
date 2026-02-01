"""
发票管理路由
Invoice Management Routes
"""

from fastapi import APIRouter, HTTPException, status, Depends, Query, UploadFile, File
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import date
from decimal import Decimal
from auth.dependencies import require_permission
from auth.middleware.auth_middleware import CurrentUser
from invoice.invoice_service import get_invoice_service
from core.invoice_models import InvoiceType, InvoiceDirection, InvoiceStatus, TaxRate
from infra.logger import get_logger

log = get_logger("InvoiceRoutes")
router = APIRouter(prefix="/invoices", tags=["发票管理"])


# ==================== Schemas ====================

class InvoiceItemRequest(BaseModel):
    goods_name: str
    specification: Optional[str] = None
    unit: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    amount: float
    tax_rate: Optional[str] = None
    tax_amount: Optional[float] = None
    goods_code: Optional[str] = None
    tax_category_code: Optional[str] = None


class InvoiceCreateRequest(BaseModel):
    invoice_code: str = Field(..., min_length=10, max_length=20)
    invoice_number: str = Field(..., min_length=8, max_length=20)
    invoice_type: str  # VAT_SPECIAL, VAT_NORMAL, VAT_ELECTRONIC, etc.
    direction: str  # INPUT, OUTPUT
    invoice_date: date
    amount_without_tax: float
    tax_amount: float
    buyer_name: str
    seller_name: str
    check_code: Optional[str] = None
    tax_rate: Optional[str] = None
    buyer_tax_id: Optional[str] = None
    seller_tax_id: Optional[str] = None
    buyer_address_phone: Optional[str] = None
    seller_address_phone: Optional[str] = None
    buyer_bank_account: Optional[str] = None
    seller_bank_account: Optional[str] = None
    remark: Optional[str] = None
    items: Optional[List[InvoiceItemRequest]] = None


class InvoiceResponse(BaseModel):
    id: int
    invoice_code: str
    invoice_number: str
    invoice_type: str
    direction: str
    status: str
    invoice_date: date
    amount_without_tax: float
    tax_amount: float
    total_amount: float
    buyer_name: str
    seller_name: str

    class Config:
        from_attributes = True


class InvoiceMatchRequest(BaseModel):
    transaction_id: int


# ==================== 发票 CRUD ====================

@router.post("", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
async def create_invoice(
    request_data: InvoiceCreateRequest,
    current_user: CurrentUser = Depends(require_permission("transactions:create"))
):
    """
    创建发票

    - 支持增值税专用发票、普通发票、电子发票等
    - 自动计算价税合计
    """
    service = get_invoice_service()

    try:
        invoice_type = InvoiceType(request_data.invoice_type)
        direction = InvoiceDirection(request_data.direction)
        tax_rate = TaxRate(request_data.tax_rate) if request_data.tax_rate else None
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    items = [item.model_dump() for item in request_data.items] if request_data.items else None

    invoice, error = service.create_invoice(
        organization_id=current_user.organization_id,
        invoice_code=request_data.invoice_code,
        invoice_number=request_data.invoice_number,
        invoice_type=invoice_type,
        direction=direction,
        invoice_date=request_data.invoice_date,
        amount_without_tax=Decimal(str(request_data.amount_without_tax)),
        tax_amount=Decimal(str(request_data.tax_amount)),
        buyer_name=request_data.buyer_name,
        seller_name=request_data.seller_name,
        items=items,
        check_code=request_data.check_code,
        tax_rate=tax_rate,
        buyer_tax_id=request_data.buyer_tax_id,
        seller_tax_id=request_data.seller_tax_id,
        remark=request_data.remark,
        user_id=current_user.user_id
    )

    if error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

    return InvoiceResponse(
        id=invoice.id,
        invoice_code=invoice.invoice_code,
        invoice_number=invoice.invoice_number,
        invoice_type=invoice.invoice_type.value,
        direction=invoice.direction.value,
        status=invoice.status.value,
        invoice_date=invoice.invoice_date,
        amount_without_tax=float(invoice.amount_without_tax),
        tax_amount=float(invoice.tax_amount),
        total_amount=float(invoice.total_amount),
        buyer_name=invoice.buyer_name,
        seller_name=invoice.seller_name
    )


@router.get("")
async def list_invoices(
    direction: Optional[str] = Query(None, description="进项/销项: INPUT/OUTPUT"),
    status: Optional[str] = Query(None, description="状态"),
    invoice_type: Optional[str] = Query(None, description="发票类型"),
    start_date: Optional[date] = Query(None, description="开始日期"),
    end_date: Optional[date] = Query(None, description="结束日期"),
    search: Optional[str] = Query(None, description="搜索关键字"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: CurrentUser = Depends(require_permission("transactions:read"))
):
    """获取发票列表"""
    service = get_invoice_service()

    dir_enum = InvoiceDirection(direction) if direction else None
    status_enum = InvoiceStatus(status) if status else None
    type_enum = InvoiceType(invoice_type) if invoice_type else None

    return service.list_invoices(
        organization_id=current_user.organization_id,
        direction=dir_enum,
        status=status_enum,
        invoice_type=type_enum,
        start_date=start_date,
        end_date=end_date,
        search=search,
        page=page,
        page_size=page_size
    )


@router.get("/{invoice_id}")
async def get_invoice(
    invoice_id: int,
    current_user: CurrentUser = Depends(require_permission("transactions:read"))
):
    """获取发票详情"""
    service = get_invoice_service()
    invoice = service.get_invoice(invoice_id, current_user.organization_id)

    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="发票不存在")

    # 获取明细行
    items = []
    for item in invoice.items:
        items.append({
            "seq": item.seq,
            "goods_name": item.goods_name,
            "specification": item.specification,
            "unit": item.unit,
            "quantity": float(item.quantity) if item.quantity else None,
            "unit_price": float(item.unit_price) if item.unit_price else None,
            "amount": float(item.amount),
            "tax_rate": item.tax_rate.value if item.tax_rate else None,
            "tax_amount": float(item.tax_amount) if item.tax_amount else None
        })

    return {
        "id": invoice.id,
        "invoice_code": invoice.invoice_code,
        "invoice_number": invoice.invoice_number,
        "invoice_type": invoice.invoice_type.value,
        "direction": invoice.direction.value,
        "status": invoice.status.value,
        "invoice_date": invoice.invoice_date.isoformat(),
        "check_code": invoice.check_code,
        "amount_without_tax": float(invoice.amount_without_tax),
        "tax_amount": float(invoice.tax_amount),
        "total_amount": float(invoice.total_amount),
        "tax_rate": invoice.tax_rate.value if invoice.tax_rate else None,
        "buyer_name": invoice.buyer_name,
        "buyer_tax_id": invoice.buyer_tax_id,
        "seller_name": invoice.seller_name,
        "seller_tax_id": invoice.seller_tax_id,
        "remark": invoice.remark,
        "items": items,
        "verification_result": invoice.verification_result,
        "verified_at": invoice.verified_at.isoformat() if invoice.verified_at else None,
        "transaction_id": invoice.transaction_id,
        "voucher_id": invoice.voucher_id
    }


# ==================== 发票验证 ====================

@router.post("/{invoice_id}/verify")
async def verify_invoice(
    invoice_id: int,
    current_user: CurrentUser = Depends(require_permission("transactions:approve"))
):
    """
    验证发票真伪

    调用税务局或第三方API验证发票
    """
    service = get_invoice_service()
    is_valid, result = service.verify_invoice(
        invoice_id=invoice_id,
        organization_id=current_user.organization_id,
        user_id=current_user.user_id
    )

    if "error" in result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])

    return {
        "invoice_id": invoice_id,
        "is_valid": is_valid,
        "verification_result": result
    }


# ==================== 发票匹配 ====================

@router.post("/{invoice_id}/match")
async def match_invoice(
    invoice_id: int,
    request_data: InvoiceMatchRequest,
    current_user: CurrentUser = Depends(require_permission("transactions:create"))
):
    """将发票关联到交易"""
    service = get_invoice_service()
    success, error = service.match_invoice_to_transaction(
        invoice_id=invoice_id,
        transaction_id=request_data.transaction_id,
        organization_id=current_user.organization_id,
        user_id=current_user.user_id
    )

    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

    return {"message": "发票匹配成功", "transaction_id": request_data.transaction_id}


# ==================== 税务统计 ====================

@router.get("/tax/summary")
async def get_tax_summary(
    year: int,
    month: int,
    current_user: CurrentUser = Depends(require_permission("reports:read"))
):
    """
    获取税务汇总

    - 进项税额、销项税额
    - 应纳税额计算
    """
    service = get_invoice_service()
    return service.get_tax_summary(
        organization_id=current_user.organization_id,
        year=year,
        month=month
    )


@router.get("/tax/statistics")
async def get_invoice_statistics(
    year: int,
    current_user: CurrentUser = Depends(require_permission("reports:read"))
):
    """获取年度发票统计"""
    service = get_invoice_service()
    return service.get_invoice_statistics(
        organization_id=current_user.organization_id,
        year=year
    )


# ==================== 发票作废 ====================

@router.post("/{invoice_id}/void")
async def void_invoice(
    invoice_id: int,
    current_user: CurrentUser = Depends(require_permission("transactions:approve"))
):
    """作废发票"""
    service = get_invoice_service()
    success, error = service.update_invoice_status(
        invoice_id=invoice_id,
        organization_id=current_user.organization_id,
        new_status=InvoiceStatus.VOIDED,
        user_id=current_user.user_id
    )

    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

    return {"message": "发票已作废"}
