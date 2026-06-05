"""
从 500.com 竞彩亚盘列表页抓取比赛最终比分

列表页 URL: https://odds.500.com/yazhi_jczq_{sale_date}.shtml
每行(tr[data-fid]) 的 td 结构:
  td[0]=场次编号(周四201) td[4]=主队 td[5]=比分(1:2) td[6]=客队
按售卖日期抓取，同一天所有比赛只需一次请求。
"""

import logging
from typing import Dict, Optional, Tuple

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://odds.500.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# 缓存: {sale_date: {match_code: (home, away)}}
_score_cache: Dict[str, Dict[str, Tuple[int, int]]] = {}


def _parse_score(text: str) -> Optional[Tuple[int, int]]:
    if not text or ":" not in text:
        return None
    parts = text.split(":")
    if len(parts) != 2:
        return None
    try:
        return (int(parts[0].strip()), int(parts[1].strip()))
    except (ValueError, TypeError):
        return None


def _load_list_page(sale_date: str, timeout: int = 15) -> Dict[str, Tuple[int, int]]:
    """抓取并解析某售卖日期的竞彩列表页，返回 {match_code: (home, away)}"""
    url = f"{BASE_URL}/yazhi_jczq_{sale_date}.shtml"
    result: Dict[str, Tuple[int, int]] = {}
    try:
        with httpx.Client(timeout=timeout, headers=HEADERS) as client:
            resp = client.get(url)
        if resp.status_code != 200:
            logger.warning(f"获取竞彩列表失败 {sale_date}: HTTP {resp.status_code}")
            return result
        content = resp.content.decode("gbk", errors="replace")
        soup = BeautifulSoup(content, "html.parser")
        for tr in soup.find_all("tr", attrs={"data-fid": True}):
            tds = tr.find_all("td")
            if len(tds) < 7:
                continue
            code = tds[0].get_text(strip=True)
            score = _parse_score(tds[5].get_text(strip=True))
            if code:
                result[code] = score
    except Exception as e:
        logger.warning(f"解析竞彩列表异常 {sale_date}: {e}")
    return result


def fetch_match_score(sale_date: str, match_code: str) -> Optional[Tuple[int, int]]:
    """获取指定比赛最终比分；未结束或无数据返回 None。同一日期会复用缓存"""
    if sale_date not in _score_cache:
        _score_cache[sale_date] = _load_list_page(sale_date)
    return _score_cache[sale_date].get(match_code)


def clear_cache() -> None:
    _score_cache.clear()
