"""大小球概率分布: 由市场主线和水位反推预期总进球 μ(泊松), 再给出各条线买大/买小的保本水位。

验证(2026-11, football-data 20 联赛 8 赛季 53529 场, Pinnacle 2.5 线收盘): 由 2.5 线隐含概率按泊松反推, 预测 T>=1/2/4/5 与 T=3 的
频率与实际相差大多在 1.5 个百分点内(泊松比负二项更准, T=3 略低估约 1pp)。所以相邻线(次盘口)的概率推导是可靠的。
1 个百分点的 P(T>=4) 约等于 0.046 球的 μ 偏移。

本模块只做数学, 不含任何关于阵容/阵型/风格的假设; 那些因素对 μ 的影响由调用方单独说明并标注验证状态。
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from .edge import _f, _halves, _word

MAX_GOALS = 14


def pmf(mu: float) -> List[float]:
    p = [math.exp(-mu)]
    for k in range(1, MAX_GOALS + 1):
        p.append(p[-1] * mu / k)
    return p


def outcomes(mu: float, line: float, side: str = "over") -> Dict[str, float]:
    """在总进球线 line 上买大(over)/买小(under)的五档结算概率 + 有效胜率(半赢半输按 0.5, 不含走水)。"""
    p = pmf(mu)
    out = {"全赢": 0.0, "赢半": 0.0, "走水": 0.0, "输半": 0.0, "全输": 0.0}
    hs = _halves(line)
    for t, pt in enumerate(p):
        adj = [t - h if side == "over" else h - t for h in hs]
        out[_word(adj)] += pt
    win = out["全赢"] + 0.5 * out["赢半"]
    lose = out["全输"] + 0.5 * out["输半"]
    out["eff"] = win / (win + lose) if win + lose else 0.0
    return out


def break_even_water(mu: float, line: float, side: str = "over") -> Optional[float]:
    """港式水位(赢时净赚 w, 输时亏 1)至少为多少才不亏。"""
    o = outcomes(mu, line, side)
    gain = o["全赢"] + 0.5 * o["赢半"]
    loss = o["全输"] + 0.5 * o["输半"]
    return loss / gain if gain > 1e-9 else None


def ev(mu: float, line: float, water: float, side: str = "over") -> float:
    o = outcomes(mu, line, side)
    return (o["全赢"] * water + o["赢半"] * water / 2 - o["输半"] * 0.5 - o["全输"]) * 100


def fit_mu(line: float, w_over: float, w_under: float) -> Optional[float]:
    """由主线与两边港式水位(去水后的买大有效胜率)反推 μ。水位不合理返回 None。"""
    if not (0.3 < w_over < 1.6 and 0.3 < w_under < 1.6):
        return None
    io, iu = 1 / (1 + w_over), 1 / (1 + w_under)
    target = io / (io + iu)
    lo, hi = 0.3, 7.0
    for _ in range(60):
        m = (lo + hi) / 2
        if outcomes(m, line, "over")["eff"] < target:
            lo = m
        else:
            hi = m
    return (lo + hi) / 2


def pick_source(ou: List[Dict[str, Any]]) -> Optional[Tuple[str, float, float, float]]:
    """选参考公司: Pinnacle 优先, 其次 Bet365, 再其次第一家数据完整的。返回 (公司, 线, 大水, 小水)。"""
    def ok(o):
        cu = o.get("current") or {}
        ln, a, b = _f(cu.get("line")), _f(cu.get("over")), _f(cu.get("under"))
        return (ln, a, b) if ln is not None and a is not None and b is not None and 0.3 < a < 1.6 and 0.3 < b < 1.6 else None
    for name in ("Pinnacle", "Bet365"):
        for o in ou or []:
            if o.get("bookmaker") == name and ok(o):
                return (name, *ok(o))
    for o in ou or []:
        if ok(o):
            return (o.get("bookmaker") or "?", *ok(o))
    return None


def lines_around(line: float) -> List[float]:
    base = round(line * 4) / 4
    return [x for x in [base + d * 0.25 for d in range(-2, 3)] if 1.0 <= x <= 5.5]


def ou_block(ou: List[Dict[str, Any]], delta_mu: float = 0.0, delta_note: str = "") -> str:
    """【大小球概率分布】文字块。delta_mu: 已验证因素(如战意)对 μ 的修正, 单独一行展示, 不改市场 μ。"""
    src = pick_source(ou)
    if not src:
        return ""
    name, line, wo, wu = src
    mu = fit_mu(line, wo, wu)
    if mu is None:
        return ""
    p = pmf(mu)
    dist = " / ".join(f"{k}球 {p[k] * 100:.0f}%" for k in range(0, 6)) + f" / 6球以上 {sum(p[6:]) * 100:.0f}%"
    rows = []
    for ln in lines_around(line):
        bo, bu = break_even_water(mu, ln, "over"), break_even_water(mu, ln, "under")
        fmt = lambda v: f"{v:.2f}" if v is not None and v < 9 else "-"
        rows.append(f"  {ln:g} 线: 买大需水位≥{fmt(bo)} / 买小需水位≥{fmt(bu)}")
    sens = []
    for d in (-0.3, -0.15, 0.15, 0.3):
        sens.append(f"{d:+.2f}球 → 买大{ev(mu + d, line, wo, 'over'):+.0f}%、买小{ev(mu + d, line, wu, 'under'):+.0f}%")
    s = [f"\n【大小球概率分布】(泊松模型;由 {name} 主线 {line:g}(大水{wo:g}/小水{wu:g})去水后反推预期总进球 μ={mu:.2f};"
         "这个推导在 5.35 万场历史上验证过,各线概率误差大多在 1.5 个百分点内,次盘口的概率可信)",
         f"总进球分布: {dist}",
         "各线保本水位(港式,赢时净赚;盘上水位高于它=该线买这一边相对 μ 有正期望):", *rows,
         f"若你判断真实总进球比市场 μ 高/低,在 {name} 主线 {line:g} 上按当前水位买,每注期望: " + ";".join(sens),
         "读法: 大球概率偏移 1 个百分点≈总进球偏移 0.046 球,你的判断要比市场准到 0.1 球量级才有价值;换次盘口只改变走水/输半出现的位置,概率以上面的分布为准。"]
    if delta_mu:
        adj = mu + delta_mu
        s.append(f"已验证因素修正: {delta_note or ''} μ 由 {mu:.2f} 调整为 {adj:.2f}(大球概率主线 {line:g} 上约 "
                 f"{outcomes(mu, line)['eff'] * 100:.1f}% → {outcomes(adj, line)['eff'] * 100:.1f}%)")
    return "\n".join(s)


def recent_goals_text(home: str, home_totals: List[int], away: str, away_totals: List[int]) -> str:
    """近期总进球的描述性统计(按 2.5 线)。每队至少 5 场才输出。"""
    if len(home_totals) < 5 or len(away_totals) < 5:
        return ""
    def one(name, ts):
        n = len(ts)
        return (f"{name}近 {n} 场: 场均总进球 {sum(ts) / n:.1f},≥3 球 {sum(1 for t in ts if t >= 3)}/{n},"
                f"≤1 球 {sum(1 for t in ts if t <= 1)}/{n}")
    both = (sum(home_totals) / len(home_totals) + sum(away_totals) / len(away_totals)) / 2
    return ("\n【近期总进球】(描述性统计,按 2.5 线;不含主客场与对手强弱校正)\n"
            f"{one(home, home_totals)};{one(away, away_totals)};两队近期场均总进球的平均 {both:.1f}。\n"
            "说明: 回测(5.35 万场)显示,球队过去 10 场的大球倾向对盘口之外的大小球几乎没有额外预测力(相关系数≈0),这里只用来描述风格,不当作方向证据。")
