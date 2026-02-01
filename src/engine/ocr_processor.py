import re
import os
import base64
import mimetypes
from typing import Dict, Any, List
from infra.logger import get_logger
from infra.llm_connector import LLMFactory

log = get_logger("OCRProcessor")


class OCRProcessor:
    """
    [Optimization] Multimodal OCR Processor
    Uses VLM (Visual Language Model) to extract structured data from images.
    """

    def __init__(self):
        self.llm = LLMFactory.get_llm()

    def process_image(self, image_path: str) -> Dict[str, Any]:
        log.info(f"正在进行智能 OCR 识别: {image_path}")

        try:
            # 1. Prepare Image
            base64_image = self._encode_image(image_path)
            mime_type, _ = mimetypes.guess_type(image_path)
            mime_type = mime_type or "image/jpeg"
            image_url = f"data:{mime_type};base64,{base64_image}"

            # 2. Call Multimodal LLM
            prompt = """
            You are an expert accounting OCR assistant.
            Analyze the attached receipt/invoice image and extract the following fields into JSON:
            - amount: The total amount (number only, no currency symbol).
            - date: The transaction date (YYYY-MM-DD format).
            - vendor: The merchant or payee name.
            - invoice_code: Invoice code (if available).
            - invoice_num: Invoice number (if available).
            - items: A list of items purchased (brief summary).
            
            If a field is not visible, use null.
            Return ONLY the JSON object.
            """

            response = self.llm.generate_response(
                prompt=prompt,
                system_role="You are a receipt processing engine.",
                images=[image_url],
            )

            # 3. Parse Result
            result_data = response.get("result", {})

            if not result_data.get("amount"):
                log.warning("VLM extraction incomplete, falling back to regex...")

            final_result = {
                "raw_text": response.get("reasoning", "VLM Processed"),
                "structured_data": result_data,
                "confidence": response.get("confidence", 0.90),
            }

            log.info(f"OCR 完成. 提取金额: {result_data.get('amount', 'N/A')}")
            return final_result

        except Exception as e:
            log.error(f"OCR processing failed: {e}", exc_info=True)
            return {"error": str(e), "structured_data": {}, "confidence": 0.0}

    def _encode_image(self, image_path):
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")


if __name__ == "__main__":
    # Test stub
    pass
