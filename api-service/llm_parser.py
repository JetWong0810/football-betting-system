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

SYSTEM_PROMPT = """你是体育投注信息提取助手。从OCR文字中提取投注数据，只输出JSON：

{"legs":[{"homeTeam":"主队","awayTeam":"客队","league":"联赛","matchDate":"YYYY-MM-DD","betType":"让球","selection":"客+1","odds":2.26}],"stake":500,"parlayType":"2_1"}

字段说明：
- betType只能是：胜平负、让球、大小球
- selection格式：
  - 胜平负：填"主胜"/"主平"/"主负"
  - 让球：格式为"主/客"+"正负号"+"数值"，直接反映用户选了哪个队及盘口。
    例如"韩国 0"且韩国是主队→"主-0"（主队让0球，选主队）
    例如"南非 +1"且南非是客队→"客+1"（客队受让1球，选客队）
    例如"巴西 -1.5"且巴西是主队→"主-1.5"（主队让1.5球，选主队）
    关键：看截图中显示的是哪个队名，该队是主还是客，盘口数字和符号原样保留
  - 大小球：填"大N"或"小N"，如"大2.5"
- odds：@后面的数值
- stake：投注额/投注金额数值
- parlayType：串关填"N_1"（N=赛事数），单关填null
- matchDate：开赛时间中的日期部分，格式YYYY-MM-DD
- league：联赛名称，从文中提取
- homeTeam/awayTeam：从"XX VS YY"中XX是主队，YY是客队

只输出JSON。"""


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
        max_tokens=2048,
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

    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        # 尝试修复被截断的 JSON
        for suffix in ['}]}', '"}]}', '"}}]}']:
            try:
                result = json.loads(text + suffix)
                break
            except json.JSONDecodeError:
                continue
        else:
            raise

    if "legs" not in result:
        result["legs"] = []
    if "stake" not in result:
        result["stake"] = 0
    if "parlayType" not in result:
        result["parlayType"] = None

    return result
