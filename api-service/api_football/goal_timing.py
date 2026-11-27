"""进球时段曲线(合并多场比赛): 用于滚球公平价, 修正"进球率全场均匀"的假设。

单队一个赛季只有十几个进球, 时段分布很噪, 所以只用联赛或全体合并后的曲线。
口径: 常规时间 90 分钟内的进球(含伤停补时, 按所在半场归入 31-45 或 76-90); 点球、乌龙球算进球, 罚失点球不算; 加时赛进球不计入。
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from database import get_db

# (名称, 起, 止), 止为含; 45+x 归入 31-45, 90+x 归入 76-90
BINS: List[Tuple[str, int, int]] = [("1-15", 1, 15), ("16-30", 16, 30), ("31-45+", 31, 45), ("46-60", 46, 60), ("61-75", 61, 75), ("76-90+", 76, 90)]


def bin_index(minute: int, extra: int = 0) -> Optional[int]:
    """事件分钟 -> 时段序号; 加时赛(>90)返回 None。"""
    if minute > 90:
        return None
    m = max(minute, 1)
    for i, (_, lo, hi) in enumerate(BINS):
        if lo <= m <= hi:
            return i
    return None


def curve_from_counts(counts: List[int]) -> List[float]:
    tot = sum(counts)
    return [c / tot for c in counts] if tot else [1 / len(BINS)] * len(BINS)


def share_after(minute: float, curve: List[float]) -> float:
    """比赛进行到 minute 分钟之后, 剩余进球占全场进球的比例(桶内线性插值)。minute<=0 返回 1, >=90 返回 0。"""
    if minute <= 0:
        return 1.0
    if minute >= 90:
        return 0.0
    done = 0.0
    for (_, lo, hi), share in zip(BINS, curve):
        width = hi - lo + 1
        start = lo - 1                       # 该桶之前已走过的分钟数
        if minute >= hi:
            done += share
        elif minute > start:
            done += share * (minute - start) / width
            break
        else:
            break
    return max(0.0, 1.0 - done)


def remaining_mu(mu_total: float, minute: float, curve: List[float]) -> float:
    """剩余时间的预期进球数 = 全场预期 * 剩余进球占比。(假设双方进球率同比例随时间变化; 比分和红牌对进球率的影响另算。)"""
    return mu_total * share_after(minute, curve)


def load_counts(league_id: Optional[int] = None) -> Tuple[List[int], int]:
    """从比赛库读进球分钟, 返回 (各时段进球数, 比赛场数)。league_id=None 为全部已入库联赛。"""
    sql = ("SELECT e.minute, COUNT(*) AS n FROM af_match_event e JOIN af_match m ON m.af_fixture_id=e.af_fixture_id "
           "WHERE e.type='Goal' AND e.detail<>'Missed Penalty' AND m.status IN ('FT','AET','PEN')")
    args: List = []
    if league_id is not None:
        sql += " AND m.league_id=%s"
        args.append(league_id)
    sql += " GROUP BY e.minute"
    counts = [0] * len(BINS)
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(sql, tuple(args))
        for r in cur.fetchall():
            i = bin_index(int(r["minute"]))
            if i is not None:
                counts[i] += int(r["n"])
        q = "SELECT COUNT(*) AS n FROM af_match WHERE status IN ('FT','AET','PEN')" + (" AND league_id=%s" if league_id is not None else "")
        cur.execute(q, tuple(args))
        n = int(cur.fetchone()["n"])
    return counts, n


def league_curve(league_id: Optional[int] = None, min_goals: int = 400) -> Tuple[List[float], int, str]:
    """联赛曲线; 联赛进球数不足 min_goals 就退回全体合并曲线。返回 (曲线, 进球数, 来源说明)。"""
    if league_id is not None:
        c, _ = load_counts(league_id)
        if sum(c) >= min_goals:
            return curve_from_counts(c), sum(c), "该联赛"
    c, _ = load_counts(None)
    return curve_from_counts(c), sum(c), "全体合并"
