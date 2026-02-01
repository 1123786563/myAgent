"""
财务报表路由
Financial Reports Routes
"""

from fastapi import APIRouter, HTTPException, status, Depends, Query
from fastapi.responses import StreamingResponse
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime
import io
from auth.dependencies import require_permission
from auth.middleware.auth_middleware import CurrentUser
from accounting.reports_service import get_reports_service
from accounting.export_service import get_export_service
from infra.logger import get_logger

log = get_logger("ReportsRoutes")
router = APIRouter(prefix="/reports", tags=["财务报表"])


# ==================== 资产负债表 ====================

@router.get("/balance-sheet")
async def get_balance_sheet(
    year: int,
    month: int,
    current_user: CurrentUser = Depends(require_permission("reports:read"))
):
    """
    获取资产负债表

    - 资产 = 负债 + 所有者权益
    - 自动验证平衡
    """
    service = get_reports_service()
    return service.get_balance_sheet(
        organization_id=current_user.organization_id,
        year=year,
        month=month
    )


# ==================== 利润表 ====================

@router.get("/income-statement")
async def get_income_statement(
    year: int,
    month: int,
    ytd: bool = Query(False, description="是否显示年累计"),
    current_user: CurrentUser = Depends(require_permission("reports:read"))
):
    """
    获取利润表

    - 净利润 = 收入 - 成本 - 费用
    - 支持本期和年累计
    """
    service = get_reports_service()
    return service.get_income_statement(
        organization_id=current_user.organization_id,
        year=year,
        month=month,
        is_ytd=ytd
    )


# ==================== 现金流量表 ====================

@router.get("/cash-flow")
async def get_cash_flow_statement(
    year: int,
    month: int,
    current_user: CurrentUser = Depends(require_permission("reports:read"))
):
    """
    获取现金流量表

    - 经营活动 + 投资活动 + 筹资活动
    - 自动核对期初期末现金
    """
    service = get_reports_service()
    return service.get_cash_flow_statement(
        organization_id=current_user.organization_id,
        year=year,
        month=month
    )


# ==================== 科目余额表 ====================

@router.get("/account-balances")
async def get_account_balance_report(
    year: int,
    month: int,
    account_type: Optional[str] = Query(None, description="科目类型: ASSET/LIABILITY/EQUITY/REVENUE/EXPENSE"),
    level: Optional[int] = Query(None, description="科目级次 (1-6)"),
    current_user: CurrentUser = Depends(require_permission("reports:read"))
):
    """
    获取科目余额表

    - 显示期初、本期发生、年累计、期末余额
    - 支持按类型和级次筛选
    """
    service = get_reports_service()
    return service.get_account_balance_report(
        organization_id=current_user.organization_id,
        year=year,
        month=month,
        account_type=account_type,
        level=level
    )


# ==================== 明细账 ====================

@router.get("/ledger/{account_code}")
async def get_account_ledger(
    account_code: str,
    year: int,
    month: Optional[int] = None,
    current_user: CurrentUser = Depends(require_permission("reports:read"))
):
    """
    获取科目明细账

    - 按凭证逐笔显示借贷发生额
    - 计算累计余额
    """
    service = get_reports_service()
    result = service.get_account_ledger(
        organization_id=current_user.organization_id,
        account_code=account_code,
        year=year,
        month=month
    )

    if "error" in result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])

    return result


# ==================== 报表导出 ====================

@router.get("/export/{report_type}")
async def export_report(
    report_type: str,
    year: int,
    month: int,
    format: str = Query("json", description="导出格式: json/csv/excel"),
    current_user: CurrentUser = Depends(require_permission("reports:export"))
):
    """
    导出报表

    支持格式: json, csv, excel
    支持报表: balance-sheet, income-statement, cash-flow, account-balances
    """
    reports_service = get_reports_service()
    export_service = get_export_service()

    if report_type == "balance-sheet":
        data = reports_service.get_balance_sheet(current_user.organization_id, year, month)
    elif report_type == "income-statement":
        data = reports_service.get_income_statement(current_user.organization_id, year, month)
    elif report_type == "cash-flow":
        data = reports_service.get_cash_flow_statement(current_user.organization_id, year, month)
    elif report_type == "account-balances":
        data = reports_service.get_account_balance_report(current_user.organization_id, year, month)
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"未知报表类型: {report_type}")

    if format == "json":
        return data

    elif format == "csv":
        csv_bytes = export_service.export_to_csv(data, report_type)
        filename = f"{report_type}_{year}_{month}.csv"
        return StreamingResponse(
            io.BytesIO(csv_bytes),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    elif format == "excel":
        excel_bytes = export_service.export_to_excel(data, report_type)
        filename = f"{report_type}_{year}_{month}.xlsx"
        return StreamingResponse(
            io.BytesIO(excel_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"不支持的导出格式: {format}")
