"""足彩网直播列表: match_code → fid_zgzcw。httpx, 无 CloudWAF。"""
from __future__ import annotations

import logging
import re
from typing import Dict, Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

LIVE_URL = "https://live.zgzcw.com/"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
)
_CODE_RE = re.compile(r"^周[一二三四五六日]\d{3}$")
_RANK_RE = re.compile(r"\[(\d+)\]")


def _headers() -> dict:
    return {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }


def fetch_jczq_live_map(timeout: int = 20) -> Dict[str, Dict[str, Optional[str]]]:
    """返回 {match_code: {fid, home_rank, away_rank}}。仅竞彩场次号。"""
    result: Dict[str, Dict[str, Optional[str]]] = {}
    try:
        with httpx.Client(timeout=timeout, headers=_headers(), follow_redirects=True) as client:
            resp = client.get(LIVE_URL)
        if resp.status_code != 200:
            logger.warning(f"zgzcw live HTTP {resp.status_code}")
            return result
        html = resp.content.decode("utf-8", errors="replace")
        if "CloudWAF" in html or "Please Enable JavaScript" in html:
            logger.warning("zgzcw live 被盾, 本轮无映射")
            return result
    except Exception as e:
        logger.warning(f"zgzcw live 异常: {e}")
        return result

    soup = BeautifulSoup(html, "html.parser")
    trs = soup.select("tr.matchTr") or soup.find_all("tr", attrs={"matchid": True})
    for tr in trs:
        fid = (tr.get("matchid") or "").strip()
        tds = tr.find_all("td")
        if not fid or not tds:
            continue
        code = tds[0].get_text(strip=True)
        if not _CODE_RE.match(code):
            continue
        home_rank = away_rank = None
        if len(tds) > 5:
            hm = _RANK_RE.search(tds[5].get_text(" ", strip=True))
            if hm:
                home_rank = hm.group(1)
        if len(tds) > 7:
            am = _RANK_RE.search(tds[7].get_text(" ", strip=True))
            if am:
                away_rank = am.group(1)
        result[code] = {"fid": fid, "home_rank": home_rank, "away_rank": away_rank}
    logger.info(f"zgzcw live 映射 {len(result)} 场")
    return result
