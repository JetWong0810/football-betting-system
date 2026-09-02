"""从体彩赛果 API 取全场比分。

500.com 列表页已被乐盾拦截，完赛比分改走官方
getUniformMatchResultV1.qry 的 sectionsNo999（如 '2:1'）。
未完赛该字段为空，不写入。
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

from closing_odds import fetch_match_results

logger = logging.getLogger(__name__)

_SCORE_RE = re.compile(r"^\s*(\d+)\s*[:：\-]\s*(\d+)\s*$")

# (begin, end) → {match_id: (home, away)}
_by_id_cache: Dict[Tuple[str, str], Dict[str, Tuple[int, int]]] = {}
# (begin, end) → {matchNumStr: (home, away)}  窗口内场次号通常唯一
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


def clear_score_cache() -> None:
    _by_id_cache.clear()
    _by_code_cache.clear()


def fetch_ft_scores(begin_date: str, end_date: str) -> Dict[str, Tuple[int, int]]:
    """返回 {match_id: (home, away)}，仅含已出全场比分的场次。"""
    key = (str(begin_date)[:10], str(end_date)[:10])
    if key in _by_id_cache:
        return _by_id_cache[key]
    by_id: Dict[str, Tuple[int, int]] = {}
    by_code: Dict[str, Tuple[int, int]] = {}
    try:
        rows = fetch_match_results(key[0], key[1])
    except Exception as e:
        logger.warning(f"拉取体彩赛果比分失败 {key[0]}~{key[1]}: {e}")
        _by_id_cache[key] = by_id
        _by_code_cache[key] = by_code
        return by_id
    for row in rows:
        score = parse_ft_score(row.get("sectionsNo999"))
        if not score:
            continue
        mid = str(row.get("matchId") or "").strip()
        code = str(row.get("matchNumStr") or "").strip()
        if mid:
            by_id[mid] = score
        if code:
            by_code[code] = score
    _by_id_cache[key] = by_id
    _by_code_cache[key] = by_code
    return by_id


def fetch_match_score(
    match_date: str,
    match_number: str,
    match_id: Optional[str] = None,
) -> Optional[Tuple[int, int]]:
    """按 match_id 优先、场次号兜底取全场比分。未完赛返回 None。

    match_date 可以是售卖日或开赛日，会向前后各扩 1 天覆盖跨日场。
    """
    try:
        base = datetime.strptime(str(match_date)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    begin = (base - timedelta(days=1)).isoformat()
    end = (base + timedelta(days=1)).isoformat()
    by_id = fetch_ft_scores(begin, end)
    if match_id:
        got = by_id.get(str(match_id).strip())
        if got:
            return got
    code = str(match_number or "").strip()
    if not code:
        return None
    key = (begin, end)
    return _by_code_cache.get(key, {}).get(code)
