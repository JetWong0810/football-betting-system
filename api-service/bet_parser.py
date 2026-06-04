"""投注信息解析模块

通过 DeepSeek 大模型将 OCR 文本解析为结构化投注数据
"""
import logging
from typing import Any, Dict

from llm_parser import parse_with_llm

logger = logging.getLogger(__name__)


def parse_bet_image_result(ocr_result: Dict[str, Any]) -> Dict[str, Any]:
    """解析OCR识别结果，提取投注信息

    Args:
        ocr_result: OCR识别结果，格式：
            {
                "success": True,
                "text": "完整文本",
                "details": [OCR详细结果],
                "confidence": 0.92
            }

    Returns:
        {
            "success": True,
            "data": { "legs": [...], "stake": 100, ... },
            "raw_text": "OCR识别的原始文本",
            "ocr_confidence": 0.92
        }
    """
    if not ocr_result.get("success"):
        return {
            "success": False,
            "error": ocr_result.get("error", "OCR识别失败"),
            "data": None,
            "raw_text": "",
        }

    text = ocr_result.get("text", "")
    ocr_confidence = ocr_result.get("confidence", 0.0)

    if not text:
        return {
            "success": False,
            "error": "未识别到任何文字",
            "data": None,
            "raw_text": "",
        }

    try:
        bet_info = parse_with_llm(text)

        if not bet_info.get("legs"):
            return {
                "success": False,
                "error": "未能识别到有效的投注信息，请检查图片内容",
                "data": bet_info,
                "raw_text": text,
                "ocr_confidence": ocr_confidence,
            }

        return {
            "success": True,
            "data": bet_info,
            "raw_text": text,
            "ocr_confidence": ocr_confidence,
        }

    except Exception as e:
        logger.error(f"大模型解析失败: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"解析失败: {str(e)}",
            "data": None,
            "raw_text": text,
            "ocr_confidence": ocr_confidence,
        }
