import re
import random
from typing import Dict, Any, List
from logger import get_logger

log = get_logger("OCRProcessor")

class OCRProcessor:
    """
    [Optimization Round 5] 增强型 OCR 处理器
    模拟多模态输入处理，从非结构化文本/图片（模拟）中提取关键财务要素。
    提高 L1 Agent 的输入质量。
    """
    def __init__(self):
        # 预编译正则模式
        self.patterns = {
            "date": re.compile(r'(\d{4}[-年/]\d{1,2}[-月/]\d{1,2})'),
            "amount": re.compile(r'[￥¥$]?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)'),
            "invoice_code": re.compile(r'代码[:：]?\s*(\d{10,12})'),
            "invoice_num": re.compile(r'号码[:：]?\s*(\d{8,})'),
            "vendor": re.compile(r'名称[:：]?\s*([\u4e00-\u9fa5]{2,15}(?:公司|店|行))')
        }

    def process_image(self, image_path: str) -> Dict[str, Any]:
        """
        模拟 OCR 处理流程
        在真实环境中，这里会调用 Tesseract, PaddleOCR 或 Cloud Vision API
        """
        log.info(f"正在进行 OCR 识别: {image_path}")
        
        # 1. 模拟 OCR 结果 (根据文件名或随机生成)
        raw_text = self._mock_ocr_result(image_path)
        
        # 2. 结构化提取
        structured_data = self._extract_fields(raw_text)
        
        # 3. 结果组装
        result = {
            "raw_text": raw_text,
            "structured_data": structured_data,
            "confidence": 0.95 if structured_data.get("amount") else 0.6
        }
        
        log.info(f"OCR 完成. 提取金额: {structured_data.get('amount', 'N/A')}")
        return result

    def _mock_ocr_result(self, path: str) -> str:
        """根据路径特征返回模拟文本，用于测试"""
        if "taxi" in path:
            return """
            出租车发票
            代码：1100192320
            号码：12345678
            日期：2025年03月28日
            金额：58.00
            """
        elif "meal" in path:
            return """
            餐饮服务发票
            购买方：LedgerAlpha Tech
            销售方名称：海底捞咖啡厅
            金额合计：¥ 288.50
            日期：2025-03-27
            """
        else:
            return f"通用票据\n内容未知\n{path}"

    def _extract_fields(self, text: str) -> Dict[str, Any]:
        """基于正则提取关键字段"""
        data = {}
        
        # 提取金额
        amt_matches = self.patterns["amount"].findall(text)
        if amt_matches:
            # 取数字最大的通常是总金额
            try:
                amounts = [float(m.replace(',', '')) for m in amt_matches]
                data["amount"] = max(amounts)
            except:
                pass
                
        # 提取日期
        date_match = self.patterns["date"].search(text)
        if date_match:
            data["date"] = date_match.group(1)
            
        # 提取发票代码/号码
        code_match = self.patterns["invoice_code"].search(text)
        if code_match: data["invoice_code"] = code_match.group(1)
        
        num_match = self.patterns["invoice_num"].search(text)
        if num_match: data["invoice_num"] = num_match.group(1)
        
        # 提取销售方
        vendor_match = self.patterns["vendor"].search(text)
        if vendor_match: data["vendor"] = vendor_match.group(1)
        
        return data

if __name__ == "__main__":
    ocr = OCRProcessor()
    print(ocr.process_image("uploads/taxi_receipt_001.jpg"))
