"""从体彩赛果 API 取全场比分。

500.com 列表页已被乐盾拦截，完赛比分改走官方
getUniformMatchResultV1.qry 的 sectionsNo999（如 '2:1'）。
未完赛该字段为空，不写入。
"""
from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

RESULT_API_URL = (
    "https://webapi.sporttery.cn/gateway/uniform/football/"
    "getUniformMatchResultV1.qry"
)
_SCORE_RE = re.compile(r"^\s*(\d+)\s*[:：\-]\s*(\d+)\s*$")

_by_id_cache: Dict[Tuple[str, str], Dict[str, Tuple[int, int]]] = {}
_by_code_cache: Dict[Tuple[str, str], Dict[str, Tuple[int, int]]] = {}


def parse_ft_score(text) -> Optional[Tuple[int, int]]:
    if text in (None, "", "-"):
        return None
    m = _SCORE_RE.match(str(text))
    if not m:
        return None
    h, a = int(m.group(1)), int(m.group(2))
    if h > 15 or a > 15:
        return None
    return h, a


def clear_cache() -> None:
    _by_id_cache.clear()
    _by_code_cache.clear()


def scores_from_results(rows: List[Dict]) -> Dict[str, Tuple[int, int]]:
    """从已拉取的赛果列表抽出 {match_id: (home, away)}。"""
    out: Dict[str, Tuple[int, int]] = {}
    for row in rows:
        score = parse_ft_score(row.get("sectionsNo999"))
        if not score:
            continue
        mid = str(row.get("matchId") or "").strip()
        if mid:
            out[mid] = score
    return out


def fetch_ft_scores(begin_date: str, end_date: str, timeout: int = 20) -> Dict[str, Tuple[int, int]]:
    """返回 {match_id: (home, away)}，仅含已出全场比分的场次。"""
    key = (str(begin_date)[:10], str(end_date)[:10])
    if key in _by_id_cache:
        return _by_id_cache[key]
    by_id: Dict[str, Tuple[int, int]] = {}
    by_code: Dict[str, Tuple[int, int]] = {}
    params = {
        "matchBeginDate": key[0],
        "matchEndDate": key[1],
        "leagueId": "",
        "pageSize": 100,
        "pageNo": 1,
        "isFix": 0,
        "matchPage": 1,
        "pcOrWap": 1,
    }
    fetched = 0
    try:
        with httpx.Client(timeout=timeout, headers={"User-Agent": "football-betting-system/1.0"}) as client:
            while True:
                resp = client.get(RESULT_API_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
                if not data.get("success"):
                    break
                batch = (data.get("value") or {}).get("matchResult") or []
                if not batch:
                    break
                fetched += len(batch)
                for row in batch:
                    score = parse_ft_score(row.get("sectionsNo999"))
                    if not score:
                        continue
                    mid = str(row.get("matchId") or "").strip()
                    code = str(row.get("matchNumStr") or "").strip()
                    if mid:
                        by_id[mid] = score
                    if code:
                        by_code[code] = score
                total = int((data.get("value") or {}).get("total") or 0)
                if fetched >= total or len(batch) < params["pageSize"]:
                    break
                params["pageNo"] += 1
    except Exception as e:
        logger.warning(f"拉取体彩赛果比分失败 {key[0]}~{key[1]}: {e}")
    _by_id_cache[key] = by_id
    _by_code_cache[key] = by_code
    return by_id


def fetch_match_score(sale_date: str, match_code: str) -> Optional[Tuple[int, int]]:
    """兼容旧签名：按售卖日±1 天窗口 + 场次号取分。"""
    from datetime import datetime, timedelta

    try:
        base = datetime.strptime(str(sale_date)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    begin = (base - timedelta(days=1)).isoformat()
    end = (base + timedelta(days=1)).isoformat()
    fetch_ft_scores(begin, end)
    code = str(match_code or "").strip()
    return _by_code_cache.get((begin, end), {}).get(code)
