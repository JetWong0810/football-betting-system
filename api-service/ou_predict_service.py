"""大小球独立预测, 不进亚盘 7 因子。

O1 市场信号 2.0  调盘+诱盘(诱盘内部已翻), 正向
O2 市场热度 1.5  同/近盘未调盘水位, calc_prediction 再翻一次
O3 盘口结构 1.0  Bet365 vs 同行中位; 离散大则罚置信
O4 进球对比 1.5  近期总球用 Bet365 即时盘反结算
O5 竞彩总进球 1.0  有 ttg 才用

方向内部沿用 upper=大 / lower=小, 与 calc_prediction 兼容。
标准盘钉死 Bet365, 缺则 Pinnacle → 皇冠。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from predict_service import calc_prediction

UP, DOWN, NEU = "upper", "lower", "neutral"

OU_WEIGHTS = {
    "市场信号": 2.0,
    "市场热度": 1.5,
    "盘口结构": 1.0,
    "进球对比": 1.5,
    "竞彩总进球": 1.0,
}

_VOTE_WEIGHTS = {
    "Pinnacle": 1.5,
    "Bet365": 1.2,
    "皇冠": 1.2,
    "威廉希尔": 1.0,
}
_SHARP = "Pinnacle"
_STD_FALLBACK = ("Bet365", "Pinnacle", "皇冠")
_HEAT_POOL = ("Pinnacle", "Bet365", "皇冠", "威廉希尔", "澳门", "立博", "韦德")
_HEAT_SKIP = {"最大值", "最小值", "平均值", "平均*"}
_HEAT_NEAR = 0.25
_LINE_EPS = 0.01
_WATER_EPS = 0.03
_SCORE_RE = re.compile(r"(\d+):(\d+)")
_TIME_DECAY = [
    2.0, 1.5, 1.2, 1.0, 0.8, 0.6, 0.45, 0.35, 0.25, 0.2,
    0.15, 0.12, 0.1, 0.08, 0.06, 0.05, 0.04, 0.03, 0.03, 0.02,
]


def _f(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fmt_line(v: Optional[float]) -> str:
    if v is None:
        return "?"
    x = float(v)
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    s = f"{x:.2f}".rstrip("0").rstrip(".")
    return s


def _median(vals: List[float]) -> Optional[float]:
    if not vals:
        return None
    xs = sorted(vals)
    return xs[len(xs) // 2]


def _book_name(raw: str) -> str:
    t = (raw or "").strip()
    if t in _HEAT_SKIP or "平均" in t:
        return ""
    for n in _HEAT_POOL:
        if t == n or t.startswith(n):
            return n
    return t


def _companies(ou_data) -> List[Dict[str, Any]]:
    if isinstance(ou_data, dict):
        rows = ou_data.get("companies") or []
    else:
        rows = ou_data or []
    if not isinstance(rows, list):
        return []
    out = []
    seen = set()
    for c in rows:
        if not isinstance(c, dict):
            continue
        name = _book_name(c.get("bookmaker") or "")
        if not name or name in seen:
            continue
        seen.add(name)
        row = dict(c)
        row["bookmaker"] = name
        out.append(row)
    return out


def pick_standard(companies: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], str]:
    by_name = {c.get("bookmaker"): c for c in companies}
    for name in _STD_FALLBACK:
        c = by_name.get(name)
        if c and _f((c.get("current") or {}).get("line")) is not None:
            return c, name
    for c in companies:
        if _f((c.get("current") or {}).get("line")) is not None:
            return c, c.get("bookmaker") or "未知"
    return None, ""


def _split_quarter(line: float) -> Optional[Tuple[float, float]]:
    n = round(float(line) * 4)
    r = n % 4
    if r == 1:
        return n / 4 - 0.25, n / 4 + 0.25
    if r == 3:
        return n / 4 - 0.25, n / 4 + 0.25
    return None


def _settle_half(total: float, line: float) -> str:
    if abs(total - line) < 1e-9:
        return "push"
    return "over" if total > line else "under"


def settle_ou(total: float, line: float) -> str:
    """over / under / push / half_over / half_under。四分之一球拆半。"""
    split = _split_quarter(line)
    if not split:
        return _settle_half(total, line)
    a, b = split
    sa, sb = _settle_half(total, a), _settle_half(total, b)
    overs = (sa == "over") + (sb == "over")
    unders = (sa == "under") + (sb == "under")
    if overs == 2:
        return "over"
    if unders == 2:
        return "under"
    if "over" in (sa, sb) and "push" in (sa, sb):
        return "half_over"
    if "under" in (sa, sb) and "push" in (sa, sb):
        return "half_under"
    return "push"


def over_share(result: str) -> Optional[float]:
    return {
        "over": 1.0,
        "half_over": 0.5,
        "under": 0.0,
        "half_under": 0.0,
    }.get(result)


def parse_total_goals(row: Dict[str, Any]) -> Optional[int]:
    for key in ("match", "score"):
        m = _SCORE_RE.search(str(row.get(key) or ""))
        if m:
            return int(m.group(1)) + int(m.group(2))
    hs, aws = row.get("homeScore"), row.get("awayScore")
    if hs is not None and aws is not None:
        try:
            return int(hs) + int(aws)
        except (TypeError, ValueError):
            return None
    return None


def _focus_is_home(row: Dict[str, Any], focus: str) -> Optional[bool]:
    text = str(row.get("match") or "")
    if not focus or not text:
        return None
    m = _SCORE_RE.search(text)
    if not m:
        return None
    home = text[:m.start()]
    return home == focus


def _line_dir(open_line: float, close_line: float) -> str:
    if close_line > open_line + _LINE_EPS:
        return UP
    if close_line < open_line - _LINE_EPS:
        return DOWN
    return NEU


def _pack(name: str, score: int, direction: str, reason: str,
          details: Optional[List] = None, **extra) -> Dict[str, Any]:
    out = {"name": name, "score": score, "direction": direction, "reason": reason,
           "details": details or []}
    out.update(extra)
    return out


def calc_ou_signal(companies: List[Dict[str, Any]], match_line: Optional[float]) -> Dict[str, Any]:
    """O1: 升盘=line↑。诱大=升盘+大球升水→偏小; 诱小=降盘+大球降水→偏大。"""
    if not companies:
        return _pack("市场信号", 5, NEU, "无大小球数据")

    trap_over_w = trap_under_w = 0.0
    true_up_w = true_down_w = 0.0
    trap_over_names, trap_under_names = [], []
    pinnacle_dir = pinnacle_trap = None
    movers = []
    books = []
    desc_bits = []

    for c in companies:
        book = c.get("bookmaker") or ""
        if book not in _VOTE_WEIGHTS:
            continue
        ini, cur = c.get("initial") or {}, c.get("current") or {}
        ol, cl = _f(ini.get("line")), _f(cur.get("line"))
        ow, cw = _f(ini.get("over")), _f(cur.get("over"))
        if ol is None or cl is None:
            continue
        bw = _VOTE_WEIGHTS[book]
        water = None if ow is None or cw is None else cw - ow
        hdir = _line_dir(ol, cl)
        trap_over = hdir == UP and water is not None and water >= _WATER_EPS
        trap_under = hdir == DOWN and water is not None and water <= -_WATER_EPS
        if hdir != NEU:
            movers.append(book)

        if trap_over:
            trap_over_w += bw
            trap_over_names.append(book)
        elif trap_under:
            trap_under_w += bw
            trap_under_names.append(book)
        elif hdir == UP:
            true_up_w += bw
        elif hdir == DOWN:
            true_down_w += bw

        if book == _SHARP:
            if trap_over:
                pinnacle_trap = DOWN
                pinnacle_dir = DOWN
            elif trap_under:
                pinnacle_trap = UP
                pinnacle_dir = UP
            elif hdir in (UP, DOWN):
                pinnacle_dir = hdir
            elif water is not None:
                if water <= -0.08:
                    pinnacle_dir = UP
                elif water >= 0.08:
                    pinnacle_dir = DOWN

        tag, bside = "", NEU
        if trap_under:
            tag, bside = "诱小", UP
        elif trap_over:
            tag, bside = "诱大", DOWN
        elif hdir == UP:
            tag, bside = "升盘", UP
        elif hdir == DOWN:
            tag, bside = "降盘", DOWN
        elif water is not None and water <= -_WATER_EPS:
            tag, bside = "降水", UP
        elif water is not None and water >= _WATER_EPS:
            tag, bside = "升水", DOWN
        books.append({
            "label": book,
            "openH": _fmt_line(ol),
            "closeH": _fmt_line(cl),
            "openW": round(ow, 2) if ow is not None else None,
            "closeW": round(cw, 2) if cw is not None else None,
            "diff": round(water, 2) if water is not None else 0,
            "tag": tag,
            "side": bside,
        })

    direction, score = NEU, 5
    if trap_over_w >= 1.5 and trap_over_w > trap_under_w:
        direction, score = DOWN, 8 if trap_over_w >= 2.5 else 7
        who = "、".join(trap_over_names) or "多家"
        desc_bits.append(f"{who}诱大(升盘+大球升水)→偏小")
    elif trap_under_w >= 1.5 and trap_under_w > trap_over_w:
        direction, score = UP, 8 if trap_under_w >= 2.5 else 7
        who = "、".join(trap_under_names) or "多家"
        desc_bits.append(f"{who}诱小(降盘+大球降水)→偏大")
    elif true_up_w >= 2.0 and true_up_w > true_down_w + 0.5:
        direction, score = UP, 8 if true_up_w >= 3.0 else 7
        desc_bits.append("真升盘(多家)→偏大")
    elif true_down_w >= 2.0 and true_down_w > true_up_w + 0.5:
        direction, score = DOWN, 8 if true_down_w >= 3.0 else 7
        desc_bits.append("真降盘(多家)→偏小")
    elif true_up_w >= 1.2 and true_up_w > true_down_w:
        direction, score = UP, 6
        desc_bits.append("真升盘(少数)→偏大")
    elif true_down_w >= 1.2 and true_down_w > true_up_w:
        direction, score = DOWN, 6
        desc_bits.append("真降盘(少数)→偏小")
    elif pinnacle_dir in (UP, DOWN):
        direction = pinnacle_dir
        score = 7 if pinnacle_trap else 6
        tag = "诱盘" if pinnacle_trap else "调盘/水位"
        desc_bits.append(f"Pinnacle{tag}指向{'大' if pinnacle_dir == UP else '小'}")
    else:
        desc_bits.append("盘口变动不明显")

    if direction != NEU and pinnacle_dir in (UP, DOWN) and pinnacle_dir != direction:
        score = max(5, score - 1)
        desc_bits.append("与Pinnacle分歧(降置信)")
    if direction != NEU and movers == ["Bet365"]:
        score = min(score, 6)
        desc_bits.append("仅Bet365独走(降权)")

    details = [{"name": "公司变动", "desc": "、".join(desc_bits)}]
    if books:
        tags = "、".join(f"{b['label']}{b['tag'] or '平'}" for b in books)
        details.append({"name": "投票明细", "desc": tags})
    return _pack("市场信号", score, direction, "，".join(desc_bits), details, books=books)


def calc_ou_heat(companies: List[Dict[str, Any]], match_line: Optional[float]) -> Dict[str, Any]:
    """O2: 只收未调盘且贴着 Bet365 的大球水位。大热在预测时再翻成偏小。"""
    if not companies:
        return _pack("市场热度", 5, NEU, "无大小球数据，热度不明")
    if match_line is None:
        return _pack("市场热度", 5, NEU, "无Bet365盘，热度不明")

    same_drops = same_rises = 0
    on_match_n = off_match_n = traps = line_moves = total = 0
    level_ws: List[float] = []
    books = []

    for c in companies:
        book = c.get("bookmaker") or ""
        if book not in _HEAT_POOL:
            continue
        ini, cur = c.get("initial") or {}, c.get("current") or {}
        ol, cl = _f(ini.get("line")), _f(cur.get("line"))
        ow, cw = _f(ini.get("over")), _f(cur.get("over"))
        if ol is None or cl is None or ow is None or cw is None:
            continue
        total += 1
        water = cw - ow
        exact_open = abs(ol - match_line) <= 0.01
        exact_close = abs(cl - match_line) <= 0.01
        on_match = exact_open and exact_close
        near_close = abs(cl - match_line) <= _HEAT_NEAR + 0.001
        hdir = _line_dir(ol, cl)
        trap_over = hdir == UP and water >= _WATER_EPS
        trap_under = hdir == DOWN and water <= -_WATER_EPS
        heat_ok = hdir == NEU and (on_match or near_close)

        tag, bside = "", NEU
        if trap_over:
            traps += 1
            tag, bside = "诱大", DOWN
        elif trap_under:
            traps += 1
            tag, bside = "诱小", UP
        elif hdir == UP:
            line_moves += 1
            tag, bside = "升盘", UP
        elif hdir == DOWN:
            line_moves += 1
            tag, bside = "降盘", DOWN
        elif heat_ok and water <= -_WATER_EPS:
            same_drops += 1
            tag, bside = ("降水" if on_match else "近盘降水"), UP
        elif heat_ok and water >= _WATER_EPS:
            same_rises += 1
            tag, bside = ("升水" if on_match else "近盘升水"), DOWN
        elif not near_close:
            off_match_n += 1
            tag, bside = "异盘", NEU

        if on_match and heat_ok:
            on_match_n += 1
            level_ws.append(cw)
        elif on_match:
            on_match_n += 1

        books.append({
            "label": book,
            "openH": _fmt_line(ol),
            "closeH": _fmt_line(cl),
            "openW": round(ow, 2),
            "closeW": round(cw, 2),
            "diff": round(water, 2),
            "tag": tag,
            "side": bside,
        })

    line_txt = _fmt_line(match_line)
    extra = {"books": books}
    if total < 4:
        return _pack("市场热度", 5, NEU, f"本场盘{line_txt}，公司样本不足，热度不明", **extra)

    same_moved = same_drops + same_rises
    prefix = f"本场盘{line_txt}，"
    tail = f"（水位变动{same_moved}家，同盘{on_match_n}家，共{total}家）"

    def _from_moves():
        if same_moved < 2:
            return None
        if same_moved == 2:
            if same_drops == 2:
                return _pack("市场热度", 6, UP, f"{prefix}同盘/近盘降水{same_drops}家{tail}，大热", **extra)
            if same_rises == 2:
                return _pack("市场热度", 6, DOWN, f"{prefix}同盘/近盘升水{same_rises}家{tail}，小热", **extra)
            return None
        drop_r = same_drops / same_moved
        rise_r = same_rises / same_moved
        if drop_r >= 0.75:
            return _pack("市场热度", 7, UP, f"{prefix}同盘/近盘降水{same_drops}家{tail}，大热", **extra)
        if drop_r >= 0.6:
            return _pack("市场热度", 6, UP, f"{prefix}同盘/近盘降水{same_drops}家{tail}，大略热", **extra)
        if rise_r >= 0.75:
            return _pack("市场热度", 7, DOWN, f"{prefix}同盘/近盘升水{same_rises}家{tail}，小热", **extra)
        if rise_r >= 0.6:
            return _pack("市场热度", 6, DOWN, f"{prefix}同盘/近盘升水{same_rises}家{tail}，小略热", **extra)
        return None

    moved = _from_moves()
    if moved:
        return moved
    if len(level_ws) >= 2:
        mid = sorted(level_ws)[len(level_ws) // 2]
        lv = f"（同盘未调盘{len(level_ws)}家终盘大水{mid:.2f}）"
        if mid <= 0.85:
            return _pack("市场热度", 6, UP, f"{prefix}终盘低水{lv}，大略热", **extra)
        if mid >= 1.00:
            return _pack("市场热度", 6, DOWN, f"{prefix}终盘高水{lv}，小略热", **extra)

    parts = []
    if same_drops:
        parts.append(f"{same_drops}家同盘/近盘降水")
    if same_rises:
        parts.append(f"{same_rises}家同盘/近盘升水")
    if traps:
        parts.append(f"{traps}家诱盘不计")
    if line_moves:
        parts.append(f"{line_moves}家调盘不计")
    if off_match_n:
        parts.append(f"{off_match_n}家异盘不计")
    return _pack("市场热度", 5, NEU,
                 f"{prefix}信号分歧({'，'.join(parts) or '无明显变动'})，热度不明", **extra)


def calc_ou_structure(companies: List[Dict[str, Any]], std: Optional[Dict[str, Any]],
                      std_name: str) -> Dict[str, Any]:
    """O3: Bet365 vs 去掉自身后的同行中位。离散≥1.0 中性并罚置信。"""
    close_map = {}
    open_map = {}
    up_n = down_n = flat_n = 0
    for c in companies:
        book = c.get("bookmaker") or ""
        if book not in _HEAT_POOL:
            continue
        cl = _f((c.get("current") or {}).get("line"))
        ol = _f((c.get("initial") or {}).get("line"))
        if cl is None:
            continue
        close_map[book] = cl
        if ol is not None:
            open_map[book] = ol
            d = _line_dir(ol, cl)
            if d == UP:
                up_n += 1
            elif d == DOWN:
                down_n += 1
            else:
                flat_n += 1

    std_line = _f(((std or {}).get("current") or {}).get("line"))
    std_open = _f(((std or {}).get("initial") or {}).get("line"))
    if std_line is None:
        return _pack("盘口结构", 5, NEU, "无标准盘，无法对照")

    peers = [v for k, v in close_map.items() if k != std_name]
    peer_median = _median(peers)
    all_close = list(close_map.values())
    spread = (max(all_close) - min(all_close)) if len(all_close) >= 2 else 0.0
    delta = None if peer_median is None else std_line - peer_median
    open_peers = [v for k, v in open_map.items() if k != std_name]
    open_median = _median(open_peers)

    summary = (
        f"{std_name} {_fmt_line(std_line)}（初 {_fmt_line(std_open)}）｜"
        f"中位 {_fmt_line(peer_median)}｜离散 {_fmt_line(spread)}｜"
        f"升盘 {up_n} / 降 {down_n} / 贴盘 {flat_n}"
    )
    extra = {
        "peerMedian": peer_median,
        "spread": spread,
        "delta": delta,
        "summary": summary,
        "confidencePenalty": 0,
    }
    if spread >= 1.0:
        extra["confidencePenalty"] = 10
        return _pack("盘口结构", 5, NEU, f"公司盘口离散{spread:.2f}，结构不稳", **extra)
    if spread >= 0.5:
        extra["confidencePenalty"] = 4

    direction, score = NEU, 5
    reason = f"{std_name}贴着中位"
    if delta is not None:
        if delta >= 0.5:
            direction, score = DOWN, 7
            reason = f"{std_name}比中位高{delta:.2f}（开深）→偏小"
        elif delta <= -0.5:
            direction, score = UP, 7
            reason = f"{std_name}比中位低{abs(delta):.2f}（开浅）→偏大"
        elif delta >= 0.25:
            direction, score = DOWN, 6
            reason = f"{std_name}略高于中位{delta:.2f}→略偏小"
        elif delta <= -0.25:
            direction, score = UP, 6
            reason = f"{std_name}略低于中位{abs(delta):.2f}→略偏大"

    if (
        std_open is not None and open_median is not None
        and _line_dir(std_open, std_line) == UP
        and _line_dir(open_median, peer_median or open_median) == UP
        and direction == UP
    ):
        score = min(8, score + 1)
        reason += "，共识升盘加强"
    return _pack("盘口结构", score, direction, f"{reason}。{summary}", **extra)


def calc_ou_recent(form: Optional[Dict[str, Any]], match_line: Optional[float]) -> Dict[str, Any]:
    """O4: 近 20 场总球用本场 Bet365 盘反结算, 不是历史大小球库。"""
    if match_line is None:
        return _pack("进球对比", 5, NEU, "无Bet365盘，无法反算近期")
    if not form:
        return _pack("进球对比", 5, NEU, "无近期战绩")

    home_name = form.get("homeTeamName") or ""
    away_name = form.get("awayTeamName") or ""
    samples = []
    for side, rows, focus in (
        ("home", (form.get("homeRecent") or [])[:20], home_name),
        ("away", (form.get("awayRecent") or [])[:20], away_name),
    ):
        for i, row in enumerate(rows):
            total = parse_total_goals(row)
            if total is None:
                continue
            res = settle_ou(total, match_line)
            share = over_share(res)
            if share is None:
                continue
            decay = _TIME_DECAY[i] if i < len(_TIME_DECAY) else 0.02
            venue = _focus_is_home(row, focus)
            role = 1.2 if (
                (side == "home" and venue is True) or (side == "away" and venue is False)
            ) else 1.0
            w = decay * role
            samples.append({
                "side": side, "total": total, "result": res, "share": share, "w": w, "i": i,
            })

    if len(samples) < 6:
        return _pack("进球对比", 5, NEU, f"可结算样本{len(samples)}场不足")

    w_sum = sum(s["w"] for s in samples)
    over_w = sum(s["w"] * s["share"] for s in samples)
    rate = over_w / w_sum if w_sum else 0.5
    avg = sum(s["total"] * s["w"] for s in samples) / w_sum
    gap = avg - match_line
    over_n = sum(1 for s in samples if s["result"] in ("over", "half_over"))
    under_n = sum(1 for s in samples if s["result"] in ("under", "half_under"))

    direction, score = NEU, 5
    if rate >= 0.62:
        direction, score = UP, 8 if rate >= 0.72 else 7
    elif rate <= 0.38:
        direction, score = DOWN, 8 if rate <= 0.28 else 7
    elif rate >= 0.55:
        direction, score = UP, 6
    elif rate <= 0.45:
        direction, score = DOWN, 6
    if abs(gap) >= 0.5 and direction != NEU:
        score = min(8, score + 1)

    reason = (
        f"本场盘{_fmt_line(match_line)}，近{len(samples)}场加权大球率{rate:.0%}，"
        f"场均{avg:.2f}（差{gap:+.2f}）"
    )
    details = [{
        "name": "盘路统计",
        "direction": direction,
        "desc": f"大{over_n} / 小{under_n}",
        "chart": {
            "type": "stack",
            "total": over_n + under_n,
            "items": [
                {"label": "大", "value": over_n, "side": "upper", "suffix": ""},
                {"label": "小", "value": under_n, "side": "lower", "suffix": ""},
            ],
        },
    }]
    return _pack("进球对比", score, direction, reason, details,
                 overRate=round(rate, 3), avgTotal=round(avg, 2), sample=len(samples))


def calc_ou_ttg(ttg_rows: Optional[List[Dict[str, Any]]],
                match_line: Optional[float]) -> Dict[str, Any]:
    """O5: 竞彩总进球最低赔段 vs Bet365 线。差太大只降置信。"""
    extra = {"confidencePenalty": 0}
    if match_line is None:
        return _pack("竞彩总进球", 5, NEU, "无Bet365盘", **extra)
    rows = [r for r in (ttg_rows or []) if _f(r.get("odds")) is not None]
    if not rows:
        return _pack("竞彩总进球", 5, NEU, "无竞彩总进球赔率", **extra)

    best = min(rows, key=lambda r: float(r["odds"]))
    lo = _f(best.get("min_goals"))
    hi = _f(best.get("max_goals"))
    if lo is None and hi is None:
        return _pack("竞彩总进球", 5, NEU, "总进球区间缺失", **extra)
    if lo is None:
        lo = hi
    if hi is None:
        hi = lo
    mid = (float(lo) + float(hi)) / 2.0
    gap = mid - match_line
    label = best.get("goal_range") or f"{lo}-{hi}"
    odds = float(best["odds"])

    if abs(gap) >= 0.75:
        extra["confidencePenalty"] = 6
        return _pack(
            "竞彩总进球", 5, NEU,
            f"最低赔{label}({odds:.2f})中位{mid:.1f}与365盘差{gap:+.2f}，仅降置信",
            **extra,
        )
    direction, score = NEU, 5
    if gap >= 0.25:
        direction, score = UP, 6 if gap < 0.5 else 7
        reason = f"最低赔{label}({odds:.2f})偏高段→偏大"
    elif gap <= -0.25:
        direction, score = DOWN, 6 if gap > -0.5 else 7
        reason = f"最低赔{label}({odds:.2f})偏低段→偏小"
    else:
        reason = f"最低赔{label}({odds:.2f})贴近365盘"
    return _pack("竞彩总进球", score, direction, reason, **extra)


def _analysis(factors: List[Dict[str, Any]], prediction: Dict[str, Any],
              ou_meta: Dict[str, Any]) -> str:
    d = prediction.get("direction")
    label = "大" if d == UP else "小" if d == DOWN else "中性"
    bits = [f"综合倾向{label}，置信{prediction.get('confidence', 0)}%。"]
    line = ou_meta.get("summary")
    if line:
        bits.append(line)
    for f in factors:
        if f.get("reason"):
            bits.append(f"{f['name']}：{f['reason']}")
    return " ".join(bits)


def predict_ou(
    ou_data,
    form: Optional[Dict[str, Any]] = None,
    ttg_rows: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    companies = _companies(ou_data)
    std, std_name = pick_standard(companies)
    cur = (std or {}).get("current") or {}
    ini = (std or {}).get("initial") or {}
    match_line = _f(cur.get("line"))
    open_line = _f(ini.get("line"))

    o1 = calc_ou_signal(companies, match_line)
    o2 = calc_ou_heat(companies, match_line)
    o3 = calc_ou_structure(companies, std, std_name)
    o4 = calc_ou_recent(form, match_line)
    o5 = calc_ou_ttg(ttg_rows, match_line)
    factors = [o1, o2, o3, o4, o5]

    prediction = calc_prediction(factors, OU_WEIGHTS, reverse_ctx=None)
    penalty = sum(int(f.get("confidencePenalty") or 0) for f in factors)
    if penalty:
        prediction["confidence"] = max(30, int(prediction.get("confidence") or 35) - penalty)
        prediction["confidencePenalty"] = penalty

    ou_meta = {
        "book": std_name,
        "openLine": open_line,
        "closeLine": match_line,
        "over": _f(cur.get("over")),
        "under": _f(cur.get("under")),
        "peerMedian": o3.get("peerMedian"),
        "spread": o3.get("spread"),
        "summary": o3.get("summary") or "",
    }
    prediction["analysis"] = _analysis(factors, prediction, ou_meta)
    return {"factors": factors, "prediction": prediction, "ou": ou_meta}
