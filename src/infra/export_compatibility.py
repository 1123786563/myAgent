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
        [Iteration 9] 增加多币种支持
        """
        from core.config_manager import ConfigManager
        target_path = get_path("workspace", filename)
        usd_rate = ConfigManager.get_float("fx.usd_cny", 7.2) # 默认汇率
        
        try:
            qb_data = []
            for r in records:
                qb_account = r.get('category', 'Uncategorized Expense')
                currency = r.get('currency', 'CNY')
                amount = float(r.get('amount', 0))
                
                # 如果记录不是 USD，根据 QB 偏好决定是否转换
                if currency != 'USD':
                    amount_in_usd = amount / usd_rate
                else:
                    amount_in_usd = amount

                qb_data.append({
                    'Date': r.get('created_at', '').split(' ')[0],
                    'Transaction Type': 'Expense',
                    'Num': r.get('id', ''),
                    'Name': r.get('vendor', 'Unknown'),
                    'Memo': f"AI-Processed: {r.get('trace_id', '')[:8]} | Orig: {amount} {currency}",
                    'Account': qb_account,
                    'Amount': -amount_in_usd,
                    'Currency': 'USD'
                })
            
            df = pd.DataFrame(qb_data)
            df.to_csv(target_path, index=False, encoding='utf-8')
            log.info(f"QuickBooks 多币种格式导出成功: {target_path}")
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
                # [Iteration 8] 导出格式合规性自检
                if not r.get('category'):
                    log.warning(f"跳过无科目分录: {r.get('id')}")
                    continue
                
                yy_data.append({
                    '日期': r.get('created_at', '').split(' ')[0],
                    '凭证类别': '记账凭证',
                    '摘要': f"AI-Audit: {r.get('vendor', 'Unknown')}",
                    '科目编码': r.get('category', ''),
                    '借方': r.get('amount', 0),
                    '贷方': 0,
                    '制单人': 'LedgerAlpha'
                })
            
            if not yy_data: return None
            df = pd.DataFrame(yy_data)
            # 模拟 Schema 校验
            if '科目编码' not in df.columns or df['借方'].isnull().any():
                raise ValueError("用友格式校验不通过：关键字段缺失或空值")

            df.to_csv(target_path, index=False, encoding='gbk')
            log.info(f"用友格式导出成功且通过 Schema 自检: {target_path}")
            return target_path
        except Exception as e:
            log.error(f"用友导出失败: {e}")
            return None
