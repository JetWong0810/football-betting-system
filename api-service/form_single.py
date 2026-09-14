"""近期战绩/交锋行标注竞彩胜平负单关。

500.com 基本面没有单关字段；用开赛日±1 + 主客队名去对 matches / had.is_single。
只升展示、不写库。对不上则视为非单关（宁缺勿错）。
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

from database import get_db

logger = logging.getLogger(__name__)

_SCORE_RE = re.compile(r"(\d+)\s*[:：]\s*(\d+)")
_DATE_FMTS = ("%Y-%m-%d", "%y-%m-%d", "%Y/%m/%d", "%y/%m/%d")


def parse_form_date(raw: Any) -> Optional[date]:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    s = str(raw).strip()
    if not s:
        return None
    for fmt in _DATE_FMTS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def parse_form_sides(match_text: str) -> Tuple[str, str]:
    raw = re.sub(r"\[[^\]]*\]", "", match_text or "")
    m = _SCORE_RE.search(raw)
    if not m:
        return "", ""
    return raw[:m.start()].strip(), raw[m.end():].strip()


def _names_hit(a: str, b: str) -> bool:
    x, y = (a or "").strip(), (b or "").strip()
    if not x or not y:
        return False
    return x == y or x in y or y in x


def _date_key(v: Any) -> str:
    d = parse_form_date(v)
    return d.isoformat() if d else str(v or "")


def annotate_form_singles(*lists: Optional[Iterable[Dict[str, Any]]]) -> None:
    """就地给各列表的行加上 isSingle（胜平负单固口径）。"""
    rows: List[Dict[str, Any]] = []
    for lst in lists:
        rows.extend(lst or [])
    if not rows:
        return

    parsed: List[Tuple[Dict[str, Any], Optional[date], str, str]] = []
    dates = set()
    for r in rows:
        d = parse_form_date(r.get("date"))
        home, away = parse_form_sides(r.get("match") or "")
        parsed.append((r, d, home, away))
        if d:
            dates.add(d)
            dates.add(d - timedelta(days=1))
            dates.add(d + timedelta(days=1))
        r["isSingle"] = False

    if not dates:
        return

    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                ph = ",".join(["%s"] * len(dates))
                cur.execute(
                    f"""
                    SELECT m.match_date, m.home_team_name, m.away_team_name,
                           IF(m.is_single=1 OR IFNULL(o.is_single,0)=1, 1, 0) AS is_single
                    FROM matches m
                    LEFT JOIN odds_win_draw_lose o
                      ON o.match_id = m.match_id AND o.odds_type = 'had'
                    WHERE m.match_date IN ({ph})
                    """,
                    [d.isoformat() for d in dates],
                )
                db_rows = cur.fetchall() or []
    except Exception as e:
        logger.warning("annotate_form_singles 查询失败: %s", e)
        return

    by_date: Dict[str, List[Dict[str, Any]]] = {}
    for row in db_rows:
        by_date.setdefault(_date_key(row.get("match_date")), []).append(row)

    for r, d, home, away in parsed:
        if not d or not home or not away:
            continue
        found = None
        for delta in (0, -1, 1):
            for cand in by_date.get((d + timedelta(days=delta)).isoformat(), []):
                if _names_hit(home, cand.get("home_team_name") or "") and _names_hit(
                    away, cand.get("away_team_name") or ""
                ):
                    found = int(cand.get("is_single") or 0) == 1
                    break
            if found is not None:
                break
        if found:
            r["isSingle"] = True
