"""北单胜负过关(trade.500.com/bjdcsf)。rq 正=主受让, 与亚指北单行同口径。"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

URL = "https://trade.500.com/bjdcsf/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def parse_bjdcsf(html: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    out: List[Dict[str, Any]] = []
    for tr in soup.find_all("tr", attrs={"fid": True}):
        fid = str(tr.get("fid") or "").strip()
        rq_raw = tr.get("rq")
        if not fid or rq_raw in (None, ""):
            continue
        try:
            rq = float(rq_raw)
        except (TypeError, ValueError):
            continue
        out.append({
            "fid": fid,
            "rq": rq,
            "home": (tr.get("homesxname") or "").strip(),
            "away": (tr.get("awaysxname") or "").strip(),
            "gdate": str(tr.get("gdate") or "")[:10],
        })
    return out


def fetch_bjdcsf(timeout: int = 20) -> List[Dict[str, Any]]:
    with httpx.Client(timeout=timeout, headers=HEADERS, follow_redirects=True) as client:
        resp = client.get(URL)
    if resp.status_code != 200:
        logger.warning(f"bjdcsf HTTP {resp.status_code}")
        return []
    html = resp.content.decode("gbk", errors="replace")
    return parse_bjdcsf(html)


def _team_hit(a: str, b: str) -> bool:
    a, b = (a or "").replace(" ", ""), (b or "").replace(" ", "")
    if not a or not b:
        return False
    return a == b or a in b or b in a


def match_sfgg(live: Dict[str, Any], rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    fid = str(live.get("fid_500") or "").strip()
    if fid:
        for r in rows:
            if r["fid"] == fid:
                return r
    home = (live.get("home_team_name") or "").strip()
    away = (live.get("away_team_name") or "").strip()
    date = str(live.get("match_date") or "")[:10]
    cands = [r for r in rows if _team_hit(home, r["home"])]
    if date:
        dated = [r for r in cands if r.get("gdate") == date]
        if dated:
            cands = dated
    if away:
        both = [r for r in cands if _team_hit(away, r["away"])]
        if both:
            cands = both
    if len(cands) == 1:
        return cands[0]
    return None


def to_beidan(row: Dict[str, Any]) -> Dict[str, Any]:
    rq = float(row["rq"])
    return {
        "bookmaker": "北单",
        "cid": 0,
        "raw_name": "胜负过关",
        "fid": row.get("fid"),
        "initial": {"handicap": rq},
        "current": {"handicap": rq},
    }
