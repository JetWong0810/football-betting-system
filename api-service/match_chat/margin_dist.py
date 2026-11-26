"""同盘口历史净胜分布: 用五大联赛历史上"终盘亚盘相同"的比赛的实际净胜球分布, 给上盘/下盘各结算档位的概率。

为什么不用泊松: 独立泊松在各盘口档位上低估平局(平手盘 27.3% vs 实际 31.1%)、高估大比分(主让一球档客净胜≥2球 5.0% vs 实际 4.1%),
用它算出的受让方覆盖概率会系统性偏低。这里直接用实际分布, 已包含平局偏多、大比分偏少的真实形态。

局限: 只有五大联赛及其次级联赛 30448 场(2019~2026); 历史表没有大小球线, 所以没有按本场大小球线调整
(本场总进球线高于历史均值 2.5~2.8 时, 大比分概率会更高)。
"""
from __future__ import annotations

import threading
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from database import get_db

from .edge import _halves, _word

MIN_N = 300
_lock = threading.Lock()
_cache: Optional[Dict[Tuple[str, float], Counter]] = None


def _load() -> Dict[Tuple[str, float], Counter]:
    """{(热门侧 'H'主/'A'客/'0'平手, |盘口|): Counter(热门净胜球 -> 场数)}。H: 主让, 数据源原值 asian_handicap<0。"""
    global _cache
    if _cache is not None:
        return _cache
    with _lock:
        if _cache is not None:
            return _cache
        out: Dict[Tuple[str, float], Counter] = {}
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT ROUND(asian_handicap*4)/4 AS hc, (ft_home_goals-ft_away_goals) AS d, COUNT(*) AS n "
                        "FROM team_history_matches WHERE ft_home_goals IS NOT NULL AND ft_away_goals IS NOT NULL "
                        "AND asian_handicap IS NOT NULL GROUP BY 1, 2")
            for r in cur.fetchall():
                hc, d, n = float(r["hc"]), int(r["d"]), int(r["n"])
                side = "0" if hc == 0 else ("H" if hc < 0 else "A")
                mf = d if hc <= 0 else -d                 # 热门视角净胜球(平手盘用主队视角)
                out.setdefault((side, abs(hc)), Counter())[mf] += n
        _cache = out
        return out


def reset_cache() -> None:
    global _cache
    _cache = None


def lookup(line_raw: float, table: Optional[Dict[Tuple[str, float], Counter]] = None) -> Optional[Dict[str, Any]]:
    """line_raw 为数据源原值(正=主让)。返回 {dist: Counter(热门净胜球), n, merged: 实际使用的盘口范围或 None, fav: 'H'/'A'/'0', line}。"""
    t = table if table is not None else _load()
    L = round(abs(float(line_raw)) * 4) / 4
    side = "0" if line_raw == 0 else ("H" if line_raw > 0 else "A")   # 原值正=主让=主队热门
    c = t.get((side, L), Counter())
    lo = hi = L
    if side != "0":
        for _ in range(2):                       # 样本不足时最多向两侧各合并 0.5 球(两步), 不再更宽
            if sum(c.values()) >= MIN_N:
                break
            if lo - 0.25 >= 0.25:
                lo -= 0.25
                c = c + t.get((side, lo), Counter())
            if sum(c.values()) >= MIN_N:
                break
            hi += 0.25
            c = c + t.get((side, hi), Counter())
    n = sum(c.values())
    if n < MIN_N:
        return None
    return {"dist": c, "n": n, "merged": (lo, hi) if (lo, hi) != (L, L) else None, "fav": side, "line": L}


def cover_probs(dist: Counter, line: float) -> Dict[str, float]:
    """热门(上盘)在让 `line` 球时的五档结算概率, 以及有效赢盘概率(赢半按 0.5, 不含走水)。"""
    n = sum(dist.values())
    out = {"全赢": 0.0, "赢半": 0.0, "走水": 0.0, "输半": 0.0, "全输": 0.0}
    for mf, k in dist.items():
        out[_word([mf - x for x in _halves(line)])] += k / n
    win = out["全赢"] + 0.5 * out["赢半"]
    lose = out["全输"] + 0.5 * out["输半"]
    out["eff"] = win / (win + lose) if win + lose else 0.0          # 赢半/输半各按 0.5 计入胜/负, 不含走水
    return out


def margin_text(line_raw, home: str, away: str, table: Optional[Dict[Tuple[str, float], Counter]] = None) -> str:
    try:
        lk = lookup(float(line_raw), table)
    except Exception:  # noqa: BLE001  历史表不可用时不影响其余内容
        return ""
    if not lk:
        return ""
    d, n = lk["dist"], lk["n"]
    P = lambda f: sum(v for k, v in d.items() if f(k)) / n * 100
    fav_name = home if lk["fav"] == "H" else away if lk["fav"] == "A" else None
    scope = (f"{lk['merged'][0]:g}~{lk['merged'][1]:g} 档(合并相邻盘口凑够样本)" if lk["merged"] else f"{lk['line']:g} 档") + f"共 {n} 场"
    if fav_name is None:
        return ("【同盘口历史净胜分布】五大联赛历史上终盘亚盘为平手的 %d 场(主队视角): 主胜 %.1f%% / 平 %.1f%% / 客胜 %.1f%%。"
                "平手盘没有上下盘之分;未按本场大小球线调整。" % (n, P(lambda k: k > 0), P(lambda k: k == 0), P(lambda k: k < 0)))
    other = away if fav_name == home else home
    cp = cover_probs(d, lk["line"])
    n_dec = max(1.0, n * (1 - cp["走水"]))
    se = (cp["eff"] * (1 - cp["eff"]) / n_dec) ** 0.5
    ci = (max(0.0, cp["eff"] - 1.96 * se) * 100, min(1.0, cp["eff"] + 1.96 * se) * 100)
    return (f"【同盘口历史净胜分布】五大联赛历史上终盘为「{fav_name}让{lk['line']:g}」同类的比赛({scope},热门=上盘):"
            f"{fav_name}净胜≥2球 {P(lambda k: k >= 2):.1f}% / 净胜1球 {P(lambda k: k == 1):.1f}% / 平 {P(lambda k: k == 0):.1f}% / "
            f"{other}赢1球 {P(lambda k: k == -1):.1f}% / {other}赢≥2球 {P(lambda k: k <= -2):.1f}%。"
            f"按该盘口结算,上盘({fav_name}) 全赢 {cp['全赢'] * 100:.1f}% / 赢半 {cp['赢半'] * 100:.1f}% / 走水 {cp['走水'] * 100:.1f}% / "
            f"输半 {cp['输半'] * 100:.1f}% / 全输 {cp['全输'] * 100:.1f}%,下盘({other})即相反;上盘有效赢盘概率 {cp['eff'] * 100:.1f}%"
            f"(95% 区间 {ci[0]:.1f}%~{ci[1]:.1f}%,半赢半输按 0.5,不含走水;区间包含 50% 时不能说上盘或下盘偏弱)。这是同盘口历史的实际分布(平局比泊松更常见),用它判断受让方\"覆盖多少情形\"时要按概率而不是按情形个数;"
            "仅五大联赛样本,未按本场大小球线调整(总进球线高于 2.5~2.8 时大比分概率更高),亚冠/日职等联赛的进球形态可能不同。")
