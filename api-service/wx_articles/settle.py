"""公众号推荐赛后结算。只更新 wx_article_pick.result / settled_at,不改动推荐本身。

结果: hit(全赢) | hhit(赢半) | push(走水) | hmiss(输半) | miss(全输) | void(无法结算)
口径:
- 比分取 matches.home_score/away_score(90分钟/竞彩口径,与系统其他回测一致)。
- 亚盘 ah: line 为主队让球,系统标准(负=主让,正=主受让);selection=home/away。
- 竞彩让球 rqspf: line 为整数让球,同样按主队 + line 计算(主让1球写 -1)。
- 大小球 ou: line 为总进球线;selection=over/under。
- dc 双选: home_draw=主胜或平, away_draw=客胜或平。
缺少必要的 line 或选项无法识别 -> void,不猜。
"""
from __future__ import annotations

import logging
import re
from typing import List, Optional, Tuple

from database import get_db

logger = logging.getLogger(__name__)


def _parse_line(line) -> Optional[float]:
    if line is None:
        return None
    s = str(line).strip().replace("＋", "+").replace("－", "-").replace("−", "-")
    try:
        return float(s)
    except ValueError:
        return None


def _halves(line: float) -> List[float]:
    """四分之一盘拆成两半注: -0.25 -> [0, -0.5]; 0.75 -> [0.5, 1.0]。"""
    if abs(line * 4) % 2 == 1:
        return [line - 0.25, line + 0.25]
    return [line]


def _combine(adjs: List[float]) -> str:
    """每个半注的调整后净胜值 -> 结果。"""
    w = sum(1 for x in adjs if x > 0)
    l = sum(1 for x in adjs if x < 0)
    if len(adjs) == 1:
        return "hit" if w else ("miss" if l else "push")
    if w == 2:
        return "hit"
    if l == 2:
        return "miss"
    if w == 1 and l == 0:
        return "hhit"
    if l == 1 and w == 0:
        return "hmiss"
    return "push"


def settle_pick(market: str, line, selection: str, hs: int, as_: int) -> str:
    sel = (selection or "").strip().lower()
    diff = hs - as_

    if market == "spf":
        actual = "home" if diff > 0 else ("draw" if diff == 0 else "away")
        return ("hit" if sel == actual else "miss") if sel in ("home", "draw", "away") else "void"

    if market == "dc":
        if sel == "home_draw":
            return "hit" if diff >= 0 else "miss"
        if sel == "away_draw":
            return "hit" if diff <= 0 else "miss"
        return "void"

    if market == "rqspf":
        h = _parse_line(line)
        if h is None or sel not in ("home", "draw", "away"):
            return "void"
        adj = diff + h
        actual = "home" if adj > 0 else ("draw" if adj == 0 else "away")
        return "hit" if sel == actual else "miss"

    if market == "ah":
        h = _parse_line(line)
        if h is None or sel not in ("home", "away"):
            return "void"
        sign = 1 if sel == "home" else -1
        return _combine([sign * (diff + x) for x in _halves(h)])

    if market == "ou":
        l = _parse_line(line)
        if l is None or sel not in ("over", "under"):
            return "void"
        total = hs + as_
        sign = 1 if sel == "over" else -1
        return _combine([sign * (total - x) for x in _halves(l)])

    if market == "score":
        m = re.search(r"(\d+)\s*(?:[-:：]|比|对)\s*(\d+)", sel)
        if not m:
            return "void"
        return "hit" if (int(m.group(1)), int(m.group(2))) == (hs, as_) else "miss"

    return "void"


def _system_ah_close(cur, match_id: str) -> Optional[float]:
    """系统库 Bet365 亚盘终盘(标准: 负=主让)。"""
    cur.execute("SELECT close_handicap FROM jczq_ah_history WHERE match_id=%s AND company LIKE %s "
                "AND close_handicap IS NOT NULL LIMIT 1", (match_id, "Bet365%"))
    r = cur.fetchone()
    return float(r["close_handicap"]) if r and r.get("close_handicap") is not None else None


def settle_pending() -> int:
    """结算所有已完赛比赛上的 pending 倾向,返回结算条数。

    - 让球倾向(ah)作者没给盘口线 -> 用系统终盘亚盘结算,并记录 line_source=system;
      终盘缺失时保持 pending,开赛 3 天后仍缺失则 void。
    - 大小球/竞彩让球没有线 -> void(不猜线)。
    """
    import time
    n = 0
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT p.id, p.match_id, p.market, p.line, p.selection, m.home_score, m.away_score, m.match_timestamp "
            "FROM wx_article_pick p JOIN matches m ON m.match_id=p.match_id "
            "WHERE p.result='pending' AND m.home_score IS NOT NULL AND m.away_score IS NOT NULL")
        rows = list(cur.fetchall() or [])
        for r in rows:
            line, src = r["line"], None
            if r["market"] == "ah" and _parse_line(line) is None:
                sys_line = _system_ah_close(cur, r["match_id"])
                if sys_line is None:
                    if time.time() - int(r["match_timestamp"] or 0) > 3 * 86400:
                        cur.execute("UPDATE wx_article_pick SET result='void', settled_at=NOW() WHERE id=%s AND result='pending'", (r["id"],))
                        n += cur.rowcount
                    continue
                line, src = f"{sys_line:g}", "system"
            res = settle_pick(r["market"], line, r["selection"], int(r["home_score"]), int(r["away_score"]))
            if src:
                cur.execute("UPDATE wx_article_pick SET result=%s, line=%s, line_source=%s, settled_at=NOW() "
                            "WHERE id=%s AND result='pending'", (res, line, src, r["id"]))
            else:
                cur.execute("UPDATE wx_article_pick SET result=%s, settled_at=NOW() WHERE id=%s AND result='pending'",
                            (res, r["id"]))
            n += cur.rowcount
    if n:
        logger.info("wx settle: %s picks", n)
    return n


if __name__ == "__main__":      # 自检
    cases: List[Tuple] = [
        ("spf", None, "home", 2, 1, "hit"), ("spf", None, "draw", 2, 1, "miss"),
        ("dc", None, "home_draw", 1, 1, "hit"), ("dc", None, "home_draw", 0, 1, "miss"), ("dc", None, "away_draw", 0, 0, "hit"),
        ("rqspf", "-1", "home", 2, 0, "hit"), ("rqspf", "-1", "draw", 2, 1, "hit"), ("rqspf", "+1", "away", 0, 1, "miss"), ("rqspf", "+1", "away", 0, 2, "hit"),
        ("rqspf", None, "home", 2, 0, "void"),
        # 亚盘(负=主让)
        ("ah", "-0.5", "home", 1, 0, "hit"), ("ah", "-0.5", "home", 1, 1, "miss"), ("ah", "-0.5", "away", 1, 1, "hit"),
        ("ah", "0", "home", 1, 1, "push"), ("ah", "-1", "home", 1, 0, "push"),
        ("ah", "-0.25", "home", 1, 1, "hmiss"), ("ah", "-0.25", "away", 1, 1, "hhit"),
        ("ah", "+0.25", "home", 1, 1, "hhit"), ("ah", "-0.75", "home", 1, 0, "hhit"), ("ah", "-0.75", "home", 2, 0, "hit"),
        ("ah", "+0.75", "away", 0, 1, "hhit"), ("ah", "+0.75", "away", 0, 2, "hit"),
        ("ah", None, "home", 1, 0, "void"),
        # 大小球
        ("ou", "2.5", "over", 2, 1, "hit"), ("ou", "2.5", "under", 2, 1, "miss"), ("ou", "2", "over", 1, 1, "push"),
        ("ou", "2.25", "over", 1, 1, "hmiss"), ("ou", "2.25", "under", 1, 1, "hhit"), ("ou", "2.75", "over", 2, 1, "hhit"),
        ("score", None, "2-1", 2, 1, "hit"), ("score", None, "3比2", 3, 2, "hit"), ("score", None, "3比2", 2, 3, "miss"), ("score", None, "2:1", 1, 2, "miss"), ("score", None, "胜其他", 1, 2, "void"),
        ("other", None, "x", 1, 0, "void"),
    ]
    bad = 0
    for mk, ln, sel, h, a, exp in cases:
        got = settle_pick(mk, ln, sel, h, a)
        if got != exp:
            bad += 1
            print("FAIL", mk, ln, sel, f"{h}-{a}", "expect", exp, "got", got)
    print(f"{len(cases) - bad}/{len(cases)} ok")
