"""
发票管理服务
Invoice Management Service - CRUD, Verification, Tax Calculation
"""

from typing import Optional, List, Dict, Tuple, Any
from datetime import datetime, date
from decimal import Decimal
import json
from core.db_helper import DBHelper
from core.invoice_models import (
    Invoice, InvoiceItem, InvoiceVerificationLog, TaxDeclaration,
    InvoiceType, InvoiceDirection, InvoiceStatus, TaxRate
)
from auth.services.audit_service import AuditService
from infra.logger import get_logger

log = get_logger("InvoiceService")


class InvoiceService:
    """发票管理服务"""

    def __init__(self):
        self.db = DBHelper()

    # ==================== 发票 CRUD ====================

    def create_invoice(
        self,
        organization_id: int,
        invoice_code: str,
        invoice_number: str,
        invoice_type: InvoiceType,
        direction: InvoiceDirection,
        invoice_date: date,
        amount_without_tax: Decimal,
        tax_amount: Decimal,
        buyer_name: str,
        seller_name: str,
        items: List[Dict] = None,
        check_code: str = None,
        tax_rate: TaxRate = None,
        buyer_tax_id: str = None,
        seller_tax_id: str = None,
        remark: str = None,
        attachment_url: str = None,
        user_id: int = None
    ) -> Tuple[Optional[Invoice], Optional[str]]:
        """创建发票"""
        with self.db.transaction() as session:
            # 检查发票是否已存在
            existing = session.query(Invoice).filter_by(
                organization_id=organization_id,
                invoice_code=invoice_code,
                invoice_number=invoice_number
            ).first()
            if existing:
                return None, f"发票已存在: {invoice_code}-{invoice_number}"

            # 计算价税合计
            total_amount = amount_without_tax + tax_amount

            invoice = Invoice(
                organization_id=organization_id,
                invoice_code=invoice_code,
                invoice_number=invoice_number,
                invoice_type=invoice_type,
                direction=direction,
                invoice_date=invoice_date,
                check_code=check_code,
                amount_without_tax=amount_without_tax,
                tax_amount=tax_amount,
                total_amount=total_amount,
                tax_rate=tax_rate,
                buyer_name=buyer_name,
                buyer_tax_id=buyer_tax_id,
                seller_name=seller_name,
                seller_tax_id=seller_tax_id,
                remark=remark,
                attachment_url=attachment_url,
                status=InvoiceStatus.DRAFT,
                created_by=user_id
            )
            session.add(invoice)
            session.flush()

            # 添加明细行
            if items:
                for seq, item_data in enumerate(items):
                    item = InvoiceItem(
                        invoice_id=invoice.id,
                        seq=seq + 1,
                        goods_name=item_data.get("goods_name"),
                        specification=item_data.get("specification"),
                        unit=item_data.get("unit"),
                        quantity=Decimal(str(item_data.get("quantity", 0))) if item_data.get("quantity") else None,
                        unit_price=Decimal(str(item_data.get("unit_price", 0))) if item_data.get("unit_price") else None,
                        amount=Decimal(str(item_data.get("amount", 0))),
                        tax_rate=TaxRate(item_data.get("tax_rate")) if item_data.get("tax_rate") else None,
                        tax_amount=Decimal(str(item_data.get("tax_amount", 0))) if item_data.get("tax_amount") else None,
                        goods_code=item_data.get("goods_code"),
                        tax_category_code=item_data.get("tax_category_code")
                    )
                    session.add(item)

            AuditService.log_data_change(
                action="invoice.create",
                user_id=user_id,
                organization_id=organization_id,
                resource_type="Invoice",
                resource_id=str(invoice.id),
                new_values={"code": invoice_code, "number": invoice_number, "amount": str(total_amount)}
            )

            log.info(f"Created invoice {invoice_code}-{invoice_number} for org {organization_id}")
            return invoice, None

    def get_invoice(
        self,
        invoice_id: int,
        organization_id: int
    ) -> Optional[Invoice]:
        """获取发票详情"""
        with self.db.transaction() as session:
            return session.query(Invoice).filter_by(
                id=invoice_id,
                organization_id=organization_id
            ).first()

    def list_invoices(
        self,
        organization_id: int,
        direction: Optional[InvoiceDirection] = None,
        status: Optional[InvoiceStatus] = None,
        invoice_type: Optional[InvoiceType] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """获取发票列表"""
        with self.db.transaction() as session:
            query = session.query(Invoice).filter_by(organization_id=organization_id)

            if direction:
                query = query.filter(Invoice.direction == direction)
            if status:
                query = query.filter(Invoice.status == status)
            if invoice_type:
                query = query.filter(Invoice.invoice_type == invoice_type)
            if start_date:
                query = query.filter(Invoice.invoice_date >= start_date)
            if end_date:
                query = query.filter(Invoice.invoice_date <= end_date)
            if search:
                query = query.filter(
                    (Invoice.invoice_number.contains(search)) |
                    (Invoice.buyer_name.contains(search)) |
                    (Invoice.seller_name.contains(search))
                )

            total = query.count()
            offset = (page - 1) * page_size
            invoices = query.order_by(Invoice.invoice_date.desc()).offset(offset).limit(page_size).all()

            items = []
            for inv in invoices:
                items.append({
                    "id": inv.id,
                    "invoice_code": inv.invoice_code,
                    "invoice_number": inv.invoice_number,
                    "invoice_type": inv.invoice_type.value,
                    "direction": inv.direction.value,
                    "status": inv.status.value,
                    "invoice_date": inv.invoice_date.isoformat(),
                    "amount_without_tax": float(inv.amount_without_tax),
                    "tax_amount": float(inv.tax_amount),
                    "total_amount": float(inv.total_amount),
                    "buyer_name": inv.buyer_name,
                    "seller_name": inv.seller_name,
                    "tax_rate": inv.tax_rate.value if inv.tax_rate else None
                })

            return {
                "items": items,
                "total": total,
                "page": page,
                "page_size": page_size,
                "pages": (total + page_size - 1) // page_size
            }

    def update_invoice_status(
        self,
        invoice_id: int,
        organization_id: int,
        new_status: InvoiceStatus,
        user_id: int
    ) -> Tuple[bool, Optional[str]]:
        """更新发票状态"""
        with self.db.transaction() as session:
            invoice = session.query(Invoice).filter_by(
                id=invoice_id,
                organization_id=organization_id
            ).first()

            if not invoice:
                return False, "发票不存在"

            old_status = invoice.status
            invoice.status = new_status

            AuditService.log_data_change(
                action="invoice.status_change",
                user_id=user_id,
                organization_id=organization_id,
                resource_type="Invoice",
                resource_id=str(invoice_id),
                old_values={"status": old_status.value},
                new_values={"status": new_status.value}
            )

            return True, None

    # ==================== 发票验证 ====================

    def verify_invoice(
        self,
        invoice_id: int,
        organization_id: int,
        user_id: int
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        验证发票真伪

        实际生产环境需要对接税务局或第三方验证服务
        这里提供模拟实现
        """
        with self.db.transaction() as session:
            invoice = session.query(Invoice).filter_by(
                id=invoice_id,
                organization_id=organization_id
            ).first()

            if not invoice:
                return False, {"error": "发票不存在"}

            # 模拟验证逻辑 (实际需要调用税务局API)
            verification_result = self._mock_verify_invoice(invoice)

            # 记录验证日志
            log_entry = InvoiceVerificationLog(
                invoice_id=invoice_id,
                organization_id=organization_id,
                request_data=json.dumps({
                    "invoice_code": invoice.invoice_code,
                    "invoice_number": invoice.invoice_number,
                    "invoice_date": invoice.invoice_date.isoformat(),
                    "amount": str(invoice.total_amount),
                    "check_code": invoice.check_code
                }),
                response_data=json.dumps(verification_result),
                is_valid=verification_result.get("is_valid", False),
                error_code=verification_result.get("error_code"),
                error_message=verification_result.get("error_message"),
                verification_source="MOCK",
                created_by=user_id
            )
            session.add(log_entry)

            # 更新发票状态
            if verification_result.get("is_valid"):
                invoice.status = InvoiceStatus.VERIFIED
                invoice.verified_at = datetime.utcnow()
                invoice.verified_by = user_id
            else:
                invoice.status = InvoiceStatus.REJECTED

            invoice.verification_result = json.dumps(verification_result)

            return verification_result.get("is_valid", False), verification_result

    def _mock_verify_invoice(self, invoice: Invoice) -> Dict[str, Any]:
        """模拟发票验证 (实际需要对接税务局API)"""
        # 基本格式验证
        if not invoice.invoice_code or len(invoice.invoice_code) < 10:
            return {
                "is_valid": False,
                "error_code": "INVALID_CODE",
                "error_message": "发票代码格式错误"
            }

        if not invoice.invoice_number or len(invoice.invoice_number) < 8:
            return {
                "is_valid": False,
                "error_code": "INVALID_NUMBER",
                "error_message": "发票号码格式错误"
            }

        # 模拟成功验证
        return {
            "is_valid": True,
            "verification_time": datetime.utcnow().isoformat(),
            "invoice_status": "NORMAL",
            "message": "发票验证通过"
        }

    # ==================== 税务统计 ====================

    def get_tax_summary(
        self,
        organization_id: int,
        year: int,
        month: int
    ) -> Dict[str, Any]:
        """获取税务汇总"""
        with self.db.transaction() as session:
            start_date = date(year, month, 1)
            if month == 12:
                end_date = date(year + 1, 1, 1)
            else:
                end_date = date(year, month + 1, 1)

            # 进项发票统计
            input_invoices = session.query(Invoice).filter(
                Invoice.organization_id == organization_id,
                Invoice.direction == InvoiceDirection.INPUT,
                Invoice.status.in_([InvoiceStatus.VERIFIED, InvoiceStatus.MATCHED, InvoiceStatus.POSTED]),
                Invoice.invoice_date >= start_date,
                Invoice.invoice_date < end_date
            ).all()

            input_amount = sum(inv.amount_without_tax for inv in input_invoices)
            input_tax = sum(inv.tax_amount for inv in input_invoices)

            # 销项发票统计
            output_invoices = session.query(Invoice).filter(
                Invoice.organization_id == organization_id,
                Invoice.direction == InvoiceDirection.OUTPUT,
                Invoice.status.in_([InvoiceStatus.VERIFIED, InvoiceStatus.MATCHED, InvoiceStatus.POSTED]),
                Invoice.invoice_date >= start_date,
                Invoice.invoice_date < end_date
            ).all()

            output_amount = sum(inv.amount_without_tax for inv in output_invoices)
            output_tax = sum(inv.tax_amount for inv in output_invoices)

            # 应纳税额 = 销项税 - 进项税
            tax_payable = output_tax - input_tax

            return {
                "period": f"{year}年{month}月",
                "input": {
                    "count": len(input_invoices),
                    "amount_without_tax": float(input_amount),
                    "tax_amount": float(input_tax)
                },
                "output": {
                    "count": len(output_invoices),
                    "amount_without_tax": float(output_amount),
                    "tax_amount": float(output_tax)
                },
                "summary": {
                    "tax_payable": float(tax_payable) if tax_payable > 0 else 0,
                    "tax_credit": float(abs(tax_payable)) if tax_payable < 0 else 0,
                    "is_refund": tax_payable < 0
                }
            }

    def get_invoice_statistics(
        self,
        organization_id: int,
        year: int
    ) -> Dict[str, Any]:
        """获取年度发票统计"""
        with self.db.transaction() as session:
            monthly_stats = []

            for month in range(1, 13):
                summary = self.get_tax_summary(organization_id, year, month)
                monthly_stats.append({
                    "month": month,
                    "input_count": summary["input"]["count"],
                    "input_tax": summary["input"]["tax_amount"],
                    "output_count": summary["output"]["count"],
                    "output_tax": summary["output"]["tax_amount"],
                    "tax_payable": summary["summary"]["tax_payable"],
                    "tax_credit": summary["summary"]["tax_credit"]
                })

            # 年度汇总
            total_input_tax = sum(m["input_tax"] for m in monthly_stats)
            total_output_tax = sum(m["output_tax"] for m in monthly_stats)
            total_payable = sum(m["tax_payable"] for m in monthly_stats)

            return {
                "year": year,
                "monthly_stats": monthly_stats,
                "annual_summary": {
                    "total_input_invoices": sum(m["input_count"] for m in monthly_stats),
                    "total_output_invoices": sum(m["output_count"] for m in monthly_stats),
                    "total_input_tax": total_input_tax,
                    "total_output_tax": total_output_tax,
                    "total_tax_payable": total_payable
                }
            }

    # ==================== 发票匹配 ====================

    def match_invoice_to_transaction(
        self,
        invoice_id: int,
        transaction_id: int,
        organization_id: int,
        user_id: int
    ) -> Tuple[bool, Optional[str]]:
        """将发票关联到交易"""
        with self.db.transaction() as session:
            invoice = session.query(Invoice).filter_by(
                id=invoice_id,
                organization_id=organization_id
            ).first()

            if not invoice:
                return False, "发票不存在"

            if invoice.status not in [InvoiceStatus.VERIFIED, InvoiceStatus.DRAFT]:
                return False, f"发票状态不允许匹配: {invoice.status.value}"

            invoice.transaction_id = transaction_id
            invoice.status = InvoiceStatus.MATCHED

            AuditService.log_data_change(
                action="invoice.match",
                user_id=user_id,
                organization_id=organization_id,
                resource_type="Invoice",
                resource_id=str(invoice_id),
                new_values={"transaction_id": transaction_id}
            )

            return True, None


# 单例
_invoice_service = None


def get_invoice_service() -> InvoiceService:
    """获取发票服务单例"""
    global _invoice_service
    if _invoice_service is None:
        _invoice_service = InvoiceService()
    return _invoice_service
