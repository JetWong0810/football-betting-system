"""聊天分析的"价格与先验"层: 市场先验(Pinnacle 去水)、各公司最优价与相对 Pinnacle 的期望、历史信号(本系统回测)、
AI 倾向的结算与盈亏。全部是纯函数, 方便单测; 不联网。

亚盘符号: 数据源原值 正=主让、负=主受让(与 matches.asian_handicap / odds500_*_ticks 一致)。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# ---- 回测基准(Bet365 开盘→终盘, jczq_ah_history 中 500.com 来源 32095 场已结算; 2026-11 复核, 可用 backtest_signals.py 复算) ----
# 注意: 终盘取 500.com 来源(Bet365-500, 样本更大)。company='Bet365' 来源多为 football-data 回填, 但其中约 731 场是线上抓取写入的近期记录,
# 可能把开赛后的滚球盘口当终盘(抓取端已修复, 历史行未改动); 两个来源的差异另有原因, 未查明, 所以不用它。
SIGNALS = {
    "deeper": (48.1, 6740, "上盘加深(开盘→终盘)"),
    "deeper_big": (46.3, 1470, "上盘加深≥0.5 球"),
    "shallower": (51.7, 4525, "上盘变浅"),
    "same": (50.0, 10604, "盘口不变"),
}
SIGNAL_NOTE = (
    "回测(Bet365 开盘→终盘,500.com 来源 32095 场已结算): 上盘加深后上盘赢盘率 48.1%(±1.2,n=6740,按时间三等分 48.4/47.8/48.1%;"
    "加深≥0.5 球 46.3%,±2.5,n=1470),上盘变浅 51.7%(n=4525),盘口不变 50.0%(n=10604)。效应方向稳定但幅度不大(约 2~4 个百分点)。"
    "价格口径(终盘水位,27554 场): 无差别买上盘 ROI 约 -3.8%、买下盘约 -3.0%,两边都亏掉庄家抽水,没有哪一边天然占便宜;"
    "上盘加深后买下盘 ROI -1.5%、买上盘 -5.3%(n=7625),下盘相对少亏但仍为负,即命中率的差距不足以变成正收益。"
)


def _f(x) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def classify_move(open_raw, cur_raw) -> Optional[Tuple[str, float]]:
    """上盘一侧的盘口变化。返回 (kind, 幅度) kind ∈ deeper/shallower/same; 平手盘或上盘换边返回 None。"""
    o, c = _f(open_raw), _f(cur_raw)
    if o is None or c is None or o == 0 or c == 0 or (o > 0) != (c > 0):
        return None
    d = abs(c) - abs(o)
    return ("deeper" if d > 1e-9 else "shallower" if d < -1e-9 else "same"), abs(d)


def signal_text(open_raw, cur_raw, home: str, away: str) -> str:
    mv = classify_move(open_raw, cur_raw)
    head = "【历史信号】"
    if mv is None:
        return head + "本场 Bet365 开盘→即时盘为平手盘或上盘换边,无可比的统计。" + SIGNAL_NOTE
    kind, amt = mv
    up = home if _f(cur_raw) > 0 else away
    key = "deeper_big" if kind == "deeper" and amt >= 0.49 else kind
    rate, n, label = SIGNALS[key]
    word = {"deeper": f"加深 {amt:g} 球", "shallower": f"变浅 {amt:g} 球", "same": "不变"}[kind]
    extra = "上盘加深不等于看好上盘,历史上加深后上盘反而偏弱,但价格上买下盘仍不划算。" if kind == "deeper" else ""
    return (head + f"本场 Bet365 上盘({up})开盘→即时盘 {word},对应历史分组「{label}」上盘赢盘率 {rate}%(n={n})。"
            "注意:统计的是开盘→终盘,本场尚未到终盘,仅作参考。" + extra + SIGNAL_NOTE)


# ---- 同盘口水位变动(Bet365 开盘→终盘, 盘口不变的 12384 行; backtest_signals.py 可复算) ----
WATER_SIGNALS = {
    "drop": (53.1, 1.6, 3884, "上盘水位下降超过 0.05"),
    "flat": (50.3, 1.6, 3723, "水位变化不超过 0.05"),
    "rise": (47.0, 1.7, 3397, "上盘水位上升超过 0.05"),
}
WATER_NOTE = (
    "回测(Bet365 开盘→终盘,盘口全程不变的 12384 行): 上盘水位降超过 0.05 后上盘赢盘率 53.1%(±1.6,n=3884),水位变化不超过 0.05 为 50.3%(n=3723),"
    "上盘水位升超过 0.05 为 47.0%(±1.7,n=3397);按时间三等分,降水组 52.4/52.9/53.6%、升水组 45.3/48.9/45.9%,方向稳定。"
    "但按终盘价格买,降水后买上盘 ROI -0.7%(n=4195)、升水后买下盘 -0.9%(n=3671),基本打平——水位变动的信息已被价格吸收,"
    "它说明\"资金/信息的方向\",不构成可直接下注的优势。注意:水位变动(同盘口)顺势、盘口加深(见【历史信号】)逆势,两者方向相反,不要混为一谈;"
    "统计只用了 Bet365 单家、开盘→终盘,多家公司一致性和赛前某个时点的变动没有回测。"
)


def water_signal(asian: List[Dict[str, Any]], home: str, away: str) -> Optional[Dict[str, Any]]:
    """Bet365 在盘口不变的前提下, 上盘一侧水位 开盘→即时 的变化; 再给出同盘口各公司的方向分布(描述性, 未回测)。"""
    def side_water(a):
        i, cu = a.get("initial") or {}, a.get("current") or {}
        hi, hc = _f(i.get("handicap")), _f(cu.get("handicap"))
        if hi is None or hc is None or hc == 0 or abs(hi - hc) > 1e-9:
            return None
        up_home = hc > 0
        wo, wc = _f(i.get("home" if up_home else "away")), _f(cu.get("home" if up_home else "away"))
        if wo is None or wc is None or not (0.3 < wo < 1.6 and 0.3 < wc < 1.6):
            return None
        return up_home, wo, wc
    b = next((a for a in asian or [] if a.get("bookmaker") == "Bet365"), None)
    r = side_water(b) if b else None
    if not r:
        return None
    up_home, wo, wc = r
    d = round(wc - wo, 3)                      # 避免 0.05 边界上的浮点误差
    kind = "drop" if d < -0.05 else "rise" if d > 0.05 else "flat"
    tally = {"drop": 0, "rise": 0, "flat": 0}
    for a in asian or []:
        x = side_water(a)
        if x and x[0] == up_home:
            dd = round(x[2] - x[1], 3)
            tally["drop" if dd < -0.05 else "rise" if dd > 0.05 else "flat"] += 1
    return {"kind": kind, "delta": d, "wo": wo, "wc": wc, "up": home if up_home else away, "tally": tally}


def water_signal_text(asian: List[Dict[str, Any]], home: str, away: str) -> str:
    w = water_signal(asian, home, away)
    head = "【同盘口水位信号】"
    if not w:
        return head + "本场 Bet365 开盘至今盘口已变动、为平手盘或水位异常,同盘口水位变动统计不适用。" + WATER_NOTE
    rate, ci, n, label = WATER_SIGNALS[w["kind"]]
    t = w["tally"]
    cross = (f"同盘口各公司上盘水位变化:降 {t['drop']} 家 / 升 {t['rise']} 家 / 基本不变 {t['flat']} 家(多家一致性未经回测,仅描述)。"
             if sum(t.values()) > 1 else "")
    return (head + f"本场 Bet365 盘口不变,上盘({w['up']})水位 {w['wo']:g}→{w['wc']:g}(变化 {w['delta']:+.2f}),对应历史分组「{label}」"
            f"上盘赢盘率 {rate}%(±{ci},n={n})。" + cross + WATER_NOTE)


def _devig2(w_a, w_b) -> Optional[Tuple[float, float]]:
    a, b = _f(w_a), _f(w_b)
    if a is None or b is None or a <= -1 or b <= -1:
        return None
    pa, pb = 1 / (1 + a), 1 / (1 + b)
    return pa / (pa + pb), pb / (pa + pb)


def _line_txt(h: float, home: str, away: str) -> str:
    if h == 0:
        return "平手"
    return f"{home}让{abs(h):g}" if h > 0 else f"{home}受让{abs(h):g}"


def best_price(asian: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """与 Bet365 同盘口的公司里, 主/客两侧的最高水位, 及与 Pinnacle 去水公平价相比的粗略期望。"""
    rows = []
    for a in asian or []:
        cu = a.get("current") or {}
        h, wh, wa = _f(cu.get("handicap")), _f(cu.get("home")), _f(cu.get("away"))
        if h is None or wh is None or wa is None or not (0.3 < wh < 1.6 and 0.3 < wa < 1.6):
            continue
        rows.append((a.get("bookmaker"), h, wh, wa))
    base = next((r for r in rows if r[0] == "Bet365"), None) or (rows[0] if rows else None)
    if not base:
        return None
    line = base[1]
    same = [r for r in rows if abs(r[1] - line) < 1e-9]
    bh = max(same, key=lambda r: r[2])
    ba = max(same, key=lambda r: r[3])
    out = {"line": line, "n_same": len(same), "n_all": len(rows), "home": (bh[2], bh[0]), "away": (ba[3], ba[0]),
           "pin": None, "ev_home": None, "ev_away": None}
    pin = next((r for r in same if r[0] == "Pinnacle"), None)
    if pin:
        p = _devig2(pin[2], pin[3])
        if p:
            out["pin"] = (round(p[0] * 100, 1), round(p[1] * 100, 1))
            out["ev_home"] = round((p[0] * (1 + bh[2]) - 1) * 100, 1)
            out["ev_away"] = round((p[1] * (1 + ba[3]) - 1) * 100, 1)
    return out


def best_price_text(asian: List[Dict[str, Any]], home: str, away: str) -> str:
    bp = best_price(asian)
    if not bp:
        return ""
    s = (f"【最优价】主线 {_line_txt(bp['line'], home, away)}(只比较与 Bet365 同盘口的 {bp['n_same']}/{bp['n_all']} 家公司): "
         f"{home}水最高 {bp['home'][0]:g}({bp['home'][1]}),{away}水最高 {bp['away'][0]:g}({bp['away'][1]})。")
    if bp["pin"]:
        s += (f"以 Pinnacle 去水概率为公平价({home} {bp['pin'][0]}% / {away} {bp['pin'][1]}%)粗估期望:"
              f"买{home}最优价 {bp['ev_home']:+.1f}%,买{away}最优价 {bp['ev_away']:+.1f}%。"
              "粗估假设 Pinnacle 去水即真实概率,忽略半赢半输,只说明\"某家价格相对 Pinnacle 是便宜还是贵\",不是下注建议;")
        best = max(bp["ev_home"], bp["ev_away"])
        s += ("两边期望都不为正,价格上没有可下手的一边。" if best <= 0 else
              ("最好的一边期望为正但不足 2%,在估算误差之内,不视为有价值。" if best < 2.0 else
               f"最好的一边期望约 {best:+.1f}%,价格上相对 Pinnacle 有优势,但仍需有独立证据支持该方向。"))
    else:
        s += "Pinnacle 盘口与主线不同或缺失,无法估算期望。"
    return s


def prior_text(euro: List[Dict[str, Any]], home: str, away: str) -> str:
    """市场先验: 优先 Pinnacle 欧赔去水概率, 没有则取各家平均。"""
    def probs(cu):
        try:
            w, d, l = float(cu["win"]), float(cu["draw"]), float(cu["lose"])
            s = 1 / w + 1 / d + 1 / l
            return [100 / w / s, 100 / d / s, 100 / l / s]
        except (TypeError, KeyError, ValueError, ZeroDivisionError):
            return None
    pin = next((probs(e.get("current") or {}) for e in euro or [] if e.get("bookmaker") == "Pinnacle"), None)
    src = "Pinnacle 欧赔去水"
    if not pin:
        allp = [p for p in (probs(e.get("current") or {}) for e in euro or []) if p]
        if not allp:
            return ""
        pin = [sum(p[i] for p in allp) / len(allp) for i in range(3)]
        src = f"{len(allp)} 家欧赔平均去水"
    return (f"【市场先验】{src}后,即时概率 {home}胜 {pin[0]:.1f}% / 平 {pin[1]:.1f}% / {away}胜 {pin[2]:.1f}%。"
            "这是分析的起点:市场已把公开信息(阵容状态、战绩、伤停)计入其中,只有尚未被定价的新信息(官方首发、临场伤停)才应该改变它,"
            "战绩、交锋等公开基本面不要再当作独立的加分项重复计算。")


# ---------------------------------------------------------------- 结算
def _halves(line: float) -> List[float]:
    return [line - 0.25, line + 0.25] if abs(line * 4) % 2 == 1 else [line]


def _word(adjs: List[float]) -> str:
    w = sum(1 for x in adjs if x > 0)
    l = sum(1 for x in adjs if x < 0)
    if len(adjs) == 1:
        return "全赢" if w else ("全输" if l else "走水")
    if w == 2:
        return "全赢"
    if l == 2:
        return "全输"
    if w == 1 and l == 0:
        return "赢半"
    if l == 1 and w == 0:
        return "输半"
    return "走水"


_INV = {"全赢": "全输", "全输": "全赢", "赢半": "输半", "输半": "赢半", "走水": "走水"}


def _units(word: str, w: float) -> float:
    return {"全赢": w, "赢半": w / 2, "走水": 0.0, "输半": -0.5, "全输": -1.0}[word]


def settle_ah(pick: str, line_raw, w_home, w_away, hs: int, as_: int) -> Optional[Dict[str, Any]]:
    """结算亚盘倾向。pick='上盘'/'下盘'; line_raw 为倾向发出时的盘口(正=主让)。平手盘没有上下盘, 返回 None。"""
    h, wh, wa = _f(line_raw), _f(w_home), _f(w_away)
    if pick not in ("上盘", "下盘") or h is None or h == 0 or wh is None or wa is None:
        return None
    pick_home = (pick == "上盘") == (h > 0)
    home_word = _word([(hs - as_) - x for x in _halves(h)])
    word = home_word if pick_home else _INV[home_word]
    return {"word": word, "units": round(_units(word, wh if pick_home else wa), 3), "pickHome": pick_home}


def settle_ou(pick: str, line, w_over, w_under, hs: int, as_: int) -> Optional[Dict[str, Any]]:
    ln, wo, wu = _f(line), _f(w_over), _f(w_under)
    if pick not in ("大球", "小球") or ln is None or wo is None or wu is None:
        return None
    over = _word([(hs + as_) - x for x in _halves(ln)])
    word = over if pick == "大球" else _INV[over]
    return {"word": word, "units": round(_units(word, wo if pick == "大球" else wu), 3)}


def tally(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """结算结果汇总: 命中率(半赢半输按 0.5)、ROI(每单位本金)。"""
    wins = sum(1.0 if r["word"] == "全赢" else 0.5 if r["word"] == "赢半" else 0 for r in rows)
    loss = sum(1.0 if r["word"] == "全输" else 0.5 if r["word"] == "输半" else 0 for r in rows)
    n = len(rows)
    return {"n": n, "hit": round(wins / (wins + loss) * 100, 1) if wins + loss else None,
            "roi": round(sum(r["units"] for r in rows) / n * 100, 1) if n else None}
