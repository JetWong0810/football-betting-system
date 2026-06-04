"""DeepSeek 大模型结构化解析模块

将 OCR 识别的文本通过大模型解析为结构化投注数据
"""
import json
import logging
import os
from typing import Any, Dict

from openai import OpenAI

logger = logging.getLogger(__name__)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-flash"

SYSTEM_PROMPT = """你是一个专业的体育投注信息提取助手。用户会给你一段从投注截图中OCR识别出的文字，你需要从中提取结构化的投注信息。

请严格按照以下JSON格式输出，不要输出任何其他内容：

{
  "legs": [
    {
      "homeTeam": "主队名称",
      "awayTeam": "客队名称",
      "league": "联赛名称",
      "matchDate": "YYYY-MM-DD",
      "betType": "胜平负|让球胜平负|比分|总进球|半全场",
      "selection": "投注方向，如：主胜、平局、主负、主+1、客-1、大2.5、小2.5、1:0等",
      "odds": 赔率数值
    }
  ],
  "stake": 投注金额数值,
  "parlayType": "串关方式，如2_1表示2串1，单关则为null"
}

规则：
1. legs 数组包含所有识别到的赛事，支持多场（串关）
2. 如果某个字段无法识别，字符串字段填空字符串""，数值字段填0，日期填今天
3. betType 只能是以下之一：胜平负、让球胜平负、比分、总进球、半全场
4. 赔率是大于1的小数
5. 投注金额 stake 如果无法识别则填0
6. 如果有多场赛事，parlayType 填 "N_1"（N为赛事数量），单场填 null
7. 只输出JSON，不要任何解释文字"""


def _get_client() -> OpenAI:
    if not DEEPSEEK_API_KEY:
        raise RuntimeError("DEEPSEEK_API_KEY 未配置")
    return OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)


def parse_with_llm(ocr_text: str) -> Dict[str, Any]:
    """调用 DeepSeek 大模型解析 OCR 文本为结构化投注数据

    Args:
        ocr_text: OCR 识别的完整文本

    Returns:
        解析后的结构化数据 dict
    """
    client = _get_client()

    response = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": ocr_text},
        ],
        temperature=0,
        max_tokens=512,
        response_format={"type": "json_object"},
    )

    content = response.choices[0].message.content or ""
    logger.info(f"DeepSeek 返回: {content}")

    # 去除可能的 markdown 代码块包裹
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    result = json.loads(text)

    if "legs" not in result:
        result["legs"] = []
    if "stake" not in result:
        result["stake"] = 0
    if "parlayType" not in result:
        result["parlayType"] = None

    return result
