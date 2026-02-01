import pandas as pd
import os
from infra.logger import get_logger
from utils.project_paths import get_path

log = get_logger("ExportCompatibility")

class QB_SAP_Exporter:
    """
    [Iteration 3] QuickBooks/SAP 兼容性增强导出器
    """
    def __init__(self, db_helper):
        self.db = db_helper

    def to_quickbooks_csv(self, records, filename="qb_import.csv"):
        """
        导出为 QuickBooks (QB) 标准导入格式 (IIF/CSV)
        参考格式：Date, Transaction Type, Num, Name, Memo, Account, Amount
        """
        target_path = get_path("workspace", filename)
        try:
            qb_data = []
            for r in records:
                # 简单的科目映射逻辑（实际可根据 QB 科目表配置）
                qb_account = r.get('category', 'Uncategorized Expense')
                
                qb_data.append({
                    'Date': r.get('created_at', '').split(' ')[0],
                    'Transaction Type': 'Expense',
                    'Num': r.get('id', ''),
                    'Name': r.get('vendor', 'Unknown'),
                    'Memo': f"AI-Processed: {r.get('trace_id', '')[:8]}",
                    'Account': qb_account,
                    'Amount': -float(r.get('amount', 0)) # 支出通常为负
                })
            
            df = pd.DataFrame(qb_data)
            df.to_csv(target_path, index=False, encoding='utf-8')
            log.info(f"QuickBooks 格式导出成功: {target_path}")
            return target_path
        except Exception as e:
            log.error(f"QuickBooks 导出失败: {e}")
            return None

    def to_sap_concur_xml(self, records, filename="sap_concur.xml"):
        """
        导出为 SAP Concur 报销系统 XML 格式 (简化版)
        """
        import xml.etree.ElementTree as ET
        from datetime import datetime

        target_path = get_path("workspace", filename)
        try:
            root = ET.Element("Batch")
            root.set("Created", datetime.now().isoformat())
            
            for r in records:
                entry = ET.SubElement(root, "ExpenseEntry")
                ET.SubElement(entry, "Vendor").text = r.get('vendor', 'Unknown')
                ET.SubElement(entry, "Amount").text = str(r.get('amount', '0'))
                ET.SubElement(entry, "Currency").text = "CNY"
                ET.SubElement(entry, "Date").text = r.get('created_at', '').split(' ')[0]
                ET.SubElement(entry, "ExpenseType").text = r.get('category', 'General')
                ET.SubElement(entry, "ExternalID").text = str(r.get('id', ''))
                
            tree = ET.ElementTree(root)
            tree.write(target_path, encoding='utf-8', xml_declaration=True)
            log.info(f"SAP Concur XML 格式导出成功: {target_path}")
            return target_path
        except Exception as e:
            log.error(f"SAP 导出失败: {e}")
            return None

    def to_kingdee_csv(self, records, filename="kingdee_import.csv"):
        """
        导出为金蝶标准导入格式 (精简版)
        """
        target_path = get_path("workspace", filename)
        try:
            kd_data = []
            for r in records:
                kd_data.append({
                    '业务日期': r.get('created_at', '').split(' ')[0],
                    '凭证字': '记',
                    '科目': r.get('category', ''),
                    '币别': '人民币',
                    '借方金额': r.get('amount', 0),
                    '贷方金额': 0,
                    '摘要': f"{r.get('vendor', '')} AI审计确认"
                })
            pd.DataFrame(kd_data).to_csv(target_path, index=False, encoding='gbk')
            log.info(f"金蝶格式导出成功: {target_path}")
            return target_path
        except Exception as e:
            log.error(f"金蝶导出失败: {e}")
            return None

    def to_yonyou_csv(self, records, filename="yonyou_u8_import.csv"):
        """
        导出为用友 U8 标准导入格式
        """
        target_path = get_path("workspace", filename)
        try:
            yy_data = []
            for r in records:
                yy_data.append({
                    '日期': r.get('created_at', '').split(' ')[0],
                    '凭证类别': '记账凭证',
                    '摘要': f"AI-Audit: {r.get('vendor', 'Unknown')}",
                    '科目编码': r.get('category', ''),
                    '借方': r.get('amount', 0),
                    '贷方': 0,
                    '制单人': 'LedgerAlpha'
                })
            pd.DataFrame(yy_data).to_csv(target_path, index=False, encoding='gbk')
            log.info(f"用友格式导出成功: {target_path}")
            return target_path
        except Exception as e:
            log.error(f"用友导出失败: {e}")
            return None
