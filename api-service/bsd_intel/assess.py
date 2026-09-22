"""把 BSD 原样数据收成赛前推论。不进七因子。"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

POS_ORDER = {"G": 0, "D": 1, "M": 2, "F": 3}


def _f(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _i(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _eur_label(n: Optional[float]) -> str:
    if not n:
        return ""
    n = float(n)
    if n >= 1e8:
        s = f"{n / 1e8:.1f}".rstrip("0").rstrip(".")
        return f"{s}亿€"
    wan = n / 1e4
    if wan >= 100:
        return f"{wan:.0f}万€"
    if wan >= 1:
        return f"{wan:.0f}万€"
    return f"{int(n)}€"


def _name(p: Dict) -> str:
    return (p.get("short_name") or p.get("name") or "").strip()


def _short(name: str) -> str:
    raw = (name or "").strip()
    if not raw:
        return ""
    parts = raw.split()
    if not parts:
        return raw[:8]
    last = parts[-1]
    if last.lower().rstrip(".") in ("jr", "sr", "ii", "iii", "iv") and len(parts) >= 2:
        return parts[-2][:10]
    if "." in raw:
        return last[:10]
    return last[:10]


def _initials(name: str) -> str:
    raw = (name or "").replace(".", " ").strip()
    parts = [p for p in raw.split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _disp_score(avg_rating: Optional[float], profile_rating: Optional[int], role: str) -> Optional[float]:
    if avg_rating is not None:
        s = float(avg_rating)
    elif profile_rating:
        s = 4.2 + (min(95, max(50, profile_rating)) - 50) * 0.085
    else:
        return None
    if role == "主力":
        s = min(9.9, s + 0.05)
    return round(s, 1)


def _xi(block: Optional[Dict]) -> List[Dict]:
    if not block:
        return []
    return list(block.get("players") or [])


def _recent_blocks(recent: List[Dict], n: int = 5, exclude_id: Optional[int] = None) -> List[Dict]:
    rows = [g for g in (recent or []) if g.get("lineups") and g.get("side")]
    if exclude_id is not None:
        rows = [g for g in rows if g.get("event_id") != exclude_id]
    rows.sort(key=lambda g: str(g.get("event_date") or ""))
    return rows[-n:]


def _xi_ids(block: Optional[Dict]) -> List[int]:
    out = []
    for p in _xi(block):
        pid = p.get("id")
        if pid is not None:
            out.append(int(pid))
    return out


def _start_counts(recent: List[Dict], exclude_id: Optional[int] = None) -> Tuple[Dict[int, int], int]:
    cols = _recent_blocks(recent, exclude_id=exclude_id)
    cnt: Dict[int, int] = {}
    for g in cols:
        for p in _xi((g.get("lineups") or {}).get(g.get("side"))):
            pid = p.get("id")
            if pid is None:
                continue
            cnt[int(pid)] = cnt.get(int(pid), 0) + 1
    return cnt, len(cols)


def _role(starts: int, n: int) -> str:
    if n < 3:
        return "—"
    r = starts / n
    if r >= 0.7:
        return "主力"
    if r >= 0.3:
        return "轮换"
    return "边缘"


def _rows_as_list(standings: Any) -> List[Dict]:
    if not standings:
        return []
    if isinstance(standings, dict):
        return list(standings.get("standings") or standings.get("results") or [])
    return []


def _stand_row(standings: Any, team_id: Optional[int], en_name: Optional[str]) -> Optional[Dict]:
    rows = _rows_as_list(standings)
    if team_id is not None:
        for r in rows:
            if r.get("team_id") == team_id:
                return r
    if en_name:
        for r in rows:
            if r.get("team_name") == en_name:
                return r
    return None


def _agg_stats(rows: List[Dict], team_id: Optional[int], exclude_event: Optional[int]) -> Dict[str, Any]:
    seq = []
    for r in rows or []:
        if exclude_event and r.get("event_id") == exclude_event:
            continue
        seq.append(r)
    club = [r for r in seq if team_id and r.get("team_id") == team_id]
    use = club if len(club) >= 3 else seq
    use = [r for r in use if _i(r.get("minutes_played")) >= 15][:8]
    if not use:
        return {
            "apps": 0, "starts": 0, "minutes": 0,
            "goals": 0, "assists": 0, "xg": 0.0, "xa": 0.0,
            "avgRating": None,
        }
    mins = [_i(r.get("minutes_played")) for r in use]
    ratings = [_f(r.get("rating")) for r in use if _f(r.get("rating")) is not None]
    return {
        "apps": len(use),
        "starts": sum(1 for m in mins if m >= 60),
        "minutes": sum(mins),
        "goals": sum(_i(r.get("goals")) for r in use),
        "assists": sum(_i(r.get("goal_assist")) for r in use),
        "xg": round(sum(_f(r.get("expected_goals")) or 0 for r in use), 2),
        "xa": round(sum(_f(r.get("expected_assists")) or 0 for r in use), 2),
        "avgRating": round(sum(ratings) / len(ratings), 2) if ratings else None,
    }


def _age_years(dob) -> Optional[float]:
    if not dob:
        return None
    try:
        d = datetime.fromisoformat(str(dob)[:10]).date()
    except ValueError:
        return None
    today = datetime.now(timezone.utc).date()
    return (today - d).days / 365.25


def _player_card(
    p: Dict,
    *,
    team_id: Optional[int],
    starts: int,
    n_cols: int,
    in_xi: bool,
    profile: Optional[Dict],
    stats_rows: List[Dict],
    exclude_event: Optional[int],
    injured: bool,
) -> Dict[str, Any]:
    pid = p.get("id")
    agg = _agg_stats(stats_rows, team_id, exclude_event)
    value = _f((profile or {}).get("market_value_eur"))
    role = _role(starts, n_cols)
    name = _name(p) or _name(profile or {})
    prof = _i((profile or {}).get("rating")) or None
    score = _disp_score(agg.get("avgRating"), prof, role)
    age = _age_years((profile or {}).get("date_of_birth"))
    return {
        "id": pid,
        "name": name,
        "short": _short(name),
        "initials": _initials(name),
        "pos": p.get("position") or (profile or {}).get("position"),
        "num": p.get("jersey_number") if p.get("jersey_number") is not None else (profile or {}).get("jersey_number"),
        "captain": bool(p.get("captain")),
        "role": role,
        "starts": starts,
        "n": n_cols,
        "inXi": in_xi,
        "injured": injured,
        "aiScore": _f(p.get("ai_score")),
        "profileRating": prof,
        "score": score,
        "valueEur": value,
        "valueLabel": _eur_label(value),
        "age": round(age, 1) if age is not None else None,
        **agg,
    }


def _mean(xs: List[Optional[float]]) -> Optional[float]:
    vs = [x for x in xs if x is not None]
    if not vs:
        return None
    return sum(vs) / len(vs)


def _side_pack(
    name: str,
    xi_block: Dict,
    cards: List[Dict],
    last_ids: List[int],
    n_cols: int,
    stand: Optional[Dict],
    unav: List[Dict],
    dropped: List[Dict],
) -> Dict[str, Any]:
    xi = [c for c in cards if c.get("inXi")]
    vals = [c.get("valueEur") or 0 for c in xi]
    return {
        "name": name,
        "formation": (xi_block or {}).get("formation"),
        "xiConf": _pct((_f((xi_block or {}).get("confidence")) or 0) * 100) if (xi_block or {}).get("confidence") is not None else None,
        "nXi": len(xi),
        "avgProfile": round(_mean([c.get("profileRating") for c in xi]) or 0, 1) if any(c.get("profileRating") for c in xi) else None,
        "avgMatch": round(_mean([c.get("avgRating") for c in xi]) or 0, 2) if any(c.get("avgRating") for c in xi) else None,
        "valueSum": sum(vals) if any(vals) else None,
        "valueLabel": _eur_label(sum(vals)) if any(vals) else "",
        "avgAge": round(_mean([c.get("age") for c in xi]) or 0, 1) if any(c.get("age") for c in xi) else None,
        "xiGoals": sum(_i(c.get("goals")) for c in xi),
        "xiXg": round(sum(c.get("xg") or 0 for c in xi), 2),
        "regularsIn": sum(1 for c in xi if c.get("role") == "主力"),
        "regularsOut": len(dropped),
        "overlapLast": sum(1 for c in xi if c.get("id") in set(last_ids)),
        "lastN": len(last_ids) or 11,
        "lastIds": list(last_ids),
        "stand": {
            "position": stand.get("position") if stand else None,
            "pts": stand.get("pts") if stand else None,
            "played": stand.get("played") if stand else None,
            "won": stand.get("won") if stand else None,
            "form": stand.get("form") if stand else None,
            "zone": ((stand.get("zone") or {}) if stand else {}).get("key"),
            "zoneLabel": ((stand.get("zone") or {}) if stand else {}).get("label"),
            "gf": _i(stand.get("gf")) if stand and stand.get("gf") is not None else None,
            "ga": _i(stand.get("ga")) if stand and stand.get("ga") is not None else None,
            "gd": _f(stand.get("gd")) if stand else None,
            "xgf": _f(stand.get("xgf")) if stand else None,
            "xga": _f(stand.get("xga")) if stand else None,
            "xgd": _f(stand.get("xgd")) if stand else None,
            "xgGames": _i(stand.get("xg_games")) if stand else 0,
        } if stand else None,
        "unavN": len(unav or []),
        "droppedNames": [_name(x) if isinstance(x, dict) and "short_name" not in x else x.get("name") for x in dropped],
    }


def _qual(c: Optional[Dict]) -> Optional[float]:
    if not c:
        return None
    if c.get("avgRating") is not None:
        return round(float(c["avgRating"]), 2)
    if c.get("score") is not None:
        return float(c["score"])
    pr = c.get("profileRating")
    if pr:
        return round(4.2 + (min(95, max(50, int(pr))) - 50) * 0.085, 2)
    return None


def _shortn(c: Dict) -> str:
    return (c.get("short") or c.get("name") or "").strip()


def _pair_swaps(outgoing: List[Dict], incoming: List[Dict]) -> List[Tuple[Dict, Optional[Dict]]]:
    ins = list(incoming)
    pairs: List[Tuple[Dict, Optional[Dict]]] = []
    for o in sorted(outgoing, key=lambda c: _qual(c) or 0, reverse=True):
        pos = o.get("pos")
        cand = [x for x in ins if pos and x.get("pos") == pos]
        pool = cand or ins
        if not pool:
            pairs.append((o, None))
            continue
        oq = _qual(o) or 6.5
        pick = min(pool, key=lambda x: abs((_qual(x) or 6.5) - oq))
        ins.remove(pick)
        pairs.append((o, pick))
    return pairs


def _swap_impact(o: Dict, i: Optional[Dict]) -> Tuple[float, str]:
    oq = _qual(o) or 6.5
    iq = _qual(i)
    name_o = _shortn(o)
    if o.get("injured"):
        name_o += "(伤)"
    w = 1.0
    if o.get("injured"):
        w += 0.15
    if o.get("pos") == "G":
        w += 0.25
    if (o.get("xg") or 0) >= 1.5 or (_i(o.get("goals")) + _i(o.get("assists"))) >= 3:
        w += 0.2
    if iq is None:
        drop = 0.7 * w
        return drop, f"{name_o} {oq:.1f}，无对位替补，影响大"
    raw = oq - iq
    bit = f"{name_o} {oq:.1f}→{_shortn(i)} {iq:.1f}"
    if raw <= -0.15:
        return 0.0, bit + "，替上更强"
    drop = max(0.0, raw) * w
    if drop >= 0.5:
        bit += "，影响大"
    elif drop >= 0.25:
        bit += "，影响中"
    else:
        bit += "，影响小"
    return drop, bit


def _completeness(pack: Dict, cards: List[Dict]) -> Tuple[int, str, str]:
    xi = [c for c in (cards or []) if c.get("inXi")]
    dropped = [c for c in (cards or []) if (not c.get("inXi")) and c.get("role") == "主力"]
    fillers = [c for c in xi if c.get("role") in ("轮换", "边缘", "—")]
    pairs = _pair_swaps(dropped, fillers)
    score = 100
    bits = []
    drops: List[float] = []
    for o, i in pairs:
        drop, bit = _swap_impact(o, i)
        score -= drop * 24
        drops.append(drop)
        bits.append(bit)
    nxi = pack.get("nXi") or 0
    if nxi and nxi < 11:
        score -= (11 - nxi) * 8
        bits.append(f"XI 仅 {nxi} 人")
    score = max(0, min(100, int(round(score))))
    mx = max(drops) if drops else 0.0
    if mx >= 0.5:
        label = "缺主力" if score >= 50 else "残阵"
    elif score >= 85:
        label = "完整"
    elif score >= 70:
        label = "微缺"
    elif score >= 50:
        label = "缺主力"
    else:
        label = "残阵"
    return score, label, "；".join(bits) or "近况主力齐"


def _is_core(c: Dict) -> bool:
    """近况核心：常发，或进攻产出明显高于轮换水平。"""
    if c.get("role") == "主力":
        return True
    apps = _i(c.get("apps"))
    st8 = _i(c.get("starts"))
    mins = _i(c.get("minutes"))
    if apps >= 5 and (st8 >= 4 or mins >= 360):
        return True
    pos = c.get("pos")
    ga = _i(c.get("goals")) + _i(c.get("assists"))
    if pos in ("F", "M") and ga >= 3 and apps >= 3:
        return True
    xg = c.get("xg") or 0
    if pos in ("F", "M") and xg >= 1.5 and apps >= 3:
        return True
    rating = c.get("avgRating")
    if rating is not None and rating >= 7.2 and st8 >= 3:
        return True
    return False


def _rotation(pack: Dict, cards: List[Dict]) -> Tuple[int, str, str]:
    last_n = pack.get("lastN") or 11
    ov = pack.get("overlapLast") or 0
    last_chg = (1 - ov / last_n) * 100 if last_n else 50
    last_id_set = set(pack.get("lastIds") or [])
    xi = [c for c in (cards or []) if c.get("inXi")]

    if last_id_set:
        outgoing = [c for c in (cards or []) if c.get("id") in last_id_set and not c.get("inXi")]
        incoming = [c for c in xi if c.get("id") not in last_id_set]
    else:
        core = [c for c in (cards or []) if _is_core(c)]
        xi_ids = {c.get("id") for c in xi}
        outgoing = [c for c in core if c.get("id") not in xi_ids]
        incoming = [c for c in xi if not _is_core(c)]

    pairs = _pair_swaps(outgoing, incoming)
    drops: List[float] = []
    bits = []
    for o, i in pairs:
        drop, bit = _swap_impact(o, i)
        drops.append(drop)
        bits.append(bit)

    avg_drop = sum(drops) / len(drops) if drops else 0.0
    impact = min(100.0, avg_drop * 80)
    score = int(round(0.30 * last_chg + 0.70 * impact))
    score = max(0, min(100, score))
    if score <= 18:
        label = "小轮换"
    elif score <= 36:
        label = "中轮换"
    else:
        label = "大轮换"
    if drops:
        mx = max(drops)
        if mx >= 0.5:
            inj_big = any(
                o.get("injured") and d >= 0.5
                for (o, _), d in zip(pairs, drops)
            )
            label += "·伤核心" if inj_big else "·影响大"
        elif mx < 0.25:
            label += "·影响小"
    ov_bit = f"上场重叠 {ov}/{last_n}"
    detail = ov_bit + ("：" + "；".join(bits) if bits else "")
    return score, label, detail


_TOP5_PRIOR = {1: 8, 3: 7, 4: 6, 5: 6, 6: 5}  # PL / 西甲 / 意甲 / 德甲 / 法甲
HOME_ADV_GOALS = 0.30  # 能力折算盘口时用；模型 xG 已含主场
ABILITY_PTS_PER_GOAL = 25.0  # 同联赛顶对底约 1.0–1.5 球，不是 10 分 1 球


def _pct(n) -> Optional[int]:
    if n is None:
        return None
    try:
        return max(0, min(100, int(round(float(n)))))
    except (TypeError, ValueError):
        return None


def _profile_pct(r) -> Optional[float]:
    if not r:
        return None
    return (min(95.0, max(50.0, float(r))) - 50) / 45.0 * 100


def _match_pct(m) -> Optional[float]:
    if not m:
        return None
    return (min(8.5, max(5.5, float(m))) - 5.5) / 3.0 * 100


def _value_pct(v) -> Optional[float]:
    if not v or v <= 0:
        return None
    # 6.3e6→0, 1e9→100；2 倍身价大约差 21 档、加权后约 5–6 分
    x = math.log10(float(v))
    return max(0.0, min(100.0, (x - 6.8) / 1.4 * 100))


def _xgd_pct(pack: Dict) -> Optional[float]:
    st = pack.get("stand") or {}
    games = st.get("xgGames") or 0
    xgd = st.get("xgd")
    if not games or games < 3 or xgd is None:
        return None
    per = float(xgd) / games
    return max(0.0, min(100.0, (per + 1.2) / 2.4 * 100))


def _xi_xg_pct(pack: Dict) -> Optional[float]:
    xg = pack.get("xiXg")
    if xg is None:
        return None
    return max(0.0, min(100.0, float(xg) / 10.0 * 100))


def _ability_score(pack: Dict, league_id: Any = None) -> Optional[int]:
    parts: List[Tuple[float, float]] = []
    ps = _profile_pct(pack.get("avgProfile"))
    vs = _value_pct(pack.get("valueSum"))
    ms = _match_pct(pack.get("avgMatch"))
    xs = _xi_xg_pct(pack)
    gs = _xgd_pct(pack)
    if ps is not None:
        parts.append((ps, 0.35))
    if vs is not None:
        parts.append((vs, 0.25))
    if ms is not None:
        parts.append((ms, 0.15))
    if xs is not None:
        parts.append((xs, 0.10))
    if gs is not None:
        parts.append((gs, 0.15))
    if not parts:
        return None
    wsum = sum(w for _, w in parts)
    s = sum(p * w for p, w in parts) / wsum
    try:
        s += _TOP5_PRIOR.get(int(league_id), 0) if league_id is not None else 0
    except (TypeError, ValueError):
        pass
    age = pack.get("avgAge")
    if age is not None:
        if age >= 33.5:
            s -= 5
        elif age >= 32:
            s -= 3
        elif age <= 21:
            s -= 5
        elif age <= 22:
            s -= 3
    return _pct(s)


def _xg_pct(xg: Optional[float]) -> Optional[int]:
    if xg is None:
        return None
    return _pct(min(100.0, (float(xg) / 2.4) * 100))


def _ability_compare(
    home: Dict,
    away: Dict,
    hn: str,
    an: str,
    league_id: Any = None,
    is_neutral: bool = False,
) -> Dict[str, Any]:
    hv, av = home.get("valueSum") or 0, away.get("valueSum") or 0
    hm, am = home.get("avgMatch"), away.get("avgMatch")
    raw_h, raw_a = _ability_score(home, league_id), _ability_score(away, league_id)
    hs, aws = raw_h, raw_a
    lean = "even"
    if hs is not None and aws is not None:
        if hs >= aws + 6:
            lean = "home"
        elif aws >= hs + 6:
            lean = "away"
    winner = {"home": hn, "away": an, "even": "接近"}.get(lean, "接近")
    title = "接近" if lean == "even" else f"{winner}占优"
    if hs is None or aws is None:
        text = "样本不足，能力仅供参考。"
        return {"lean": lean, "title": title, "text": text, "home": hs, "away": aws, "rawHome": raw_h, "rawAway": raw_a}
    if lean == "even":
        text = f"双方 XI 综合能力接近（{hn} {hs} / {an} {aws}），不含主场"
    else:
        text = f"{winner}本场 XI 综合能力更高（{hn} {hs} / {an} {aws}），不含主场"
    text += "。"
    extra = []
    if hv and av:
        extra.append(f"身价 {home.get('valueLabel')} 对 {away.get('valueLabel')}")
    if hm and am:
        extra.append(f"近况评分 {hm:.2f} 对 {am:.2f}")
    ha, aa = home.get("avgAge"), away.get("avgAge")
    if ha is not None and (ha >= 32 or ha <= 22):
        extra.append(f"{hn} XI 均龄 {ha:.1f}")
    if aa is not None and (aa >= 32 or aa <= 22):
        extra.append(f"{an} XI 均龄 {aa:.1f}")
    if extra:
        text += extra[0] + "。" if len(extra) == 1 else "；".join(extra) + "。"
    return {"lean": lean, "title": title, "text": text, "home": hs, "away": aws, "rawHome": raw_h, "rawAway": raw_a}


def _xg_compare(home: Dict, away: Dict, pred: Optional[Dict], hn: str, an: str) -> Dict[str, Any]:
    markets = (pred or {}).get("markets") or {}
    eg = markets.get("expected_goals") or {}
    ph, pa = _f(eg.get("home")), _f(eg.get("away"))

    def per90(pack):
        st = pack.get("stand") or {}
        games = st.get("xgGames") or 0
        xgf = st.get("xgf")
        if xgf is None or games <= 0:
            return None
        return xgf / games

    hx, ax = per90(home), per90(away)
    src_h = ph if ph is not None else hx
    src_a = pa if pa is not None else ax
    hs, aws = _xg_pct(src_h), _xg_pct(src_a)
    lean = "even"
    if src_h is not None and src_a is not None:
        if src_a >= src_h + 0.25:
            lean = "away"
        elif src_h >= src_a + 0.25:
            lean = "home"
    title = "接近" if lean == "even" else f"{hn if lean == 'home' else an}更高"
    if src_h is None or src_a is None:
        text = "缺少 xG，进球期望仅供参考。"
    elif lean == "even":
        text = f"双方进球期望接近（{hn} {hs} / {an} {aws}）"
        if ph is not None and pa is not None:
            text += f"，模型 {ph:.2f}-{pa:.2f}"
        text += "。差距不到四分之一球。"
    else:
        w = hn if lean == "home" else an
        text = f"{w}进球期望更高（{hn} {hs} / {an} {aws}）。"
        if ph is not None and pa is not None:
            text += f"模型 {ph:.2f}-{pa:.2f}。"
    return {"lean": lean, "title": title, "text": text, "home": hs, "away": aws}


def _luck_per_game(pack: Dict) -> Optional[float]:
    st = pack.get("stand") or {}
    games = st.get("xgGames") or st.get("played") or 0
    if games <= 0:
        return None
    xgf, xga = st.get("xgf"), st.get("xga")
    gf, ga = st.get("gf"), st.get("ga")
    if xgf is not None and xga is not None and gf is not None and ga is not None:
        return ((float(gf) - float(xgf)) + (float(xga) - float(ga))) / games
    gd, xgd = st.get("gd"), st.get("xgd")
    if gd is not None and xgd is not None:
        return (float(gd) - float(xgd)) / games
    return None


def _overperf_compare(home: Dict, away: Dict, hn: str, an: str) -> Optional[Dict[str, Any]]:
    hl, al = _luck_per_game(home), _luck_per_game(away)
    if hl is None and al is None:
        return None
    hs = _pct(50 + (hl or 0) * 40) if hl is not None else None
    aws = _pct(50 + (al or 0) * 40) if al is not None else None
    lean = "even"
    if hs is not None and aws is not None:
        if aws >= hs + 12:
            lean = "home"
        elif hs >= aws + 12:
            lean = "away"
    inflated = None
    if lean == "home":
        inflated = an
    elif lean == "away":
        inflated = hn
    title = f"{inflated}虚高" if inflated else "接近"
    bits = []
    for name, pack, luck in ((hn, home, hl), (an, away, al)):
        st = pack.get("stand") or {}
        if luck is None:
            continue
        xgd = st.get("xgd")
        pts = st.get("pts")
        pos = st.get("position")
        tag = "虚高" if luck >= 0.6 else ("偏运" if luck >= 0.25 else ("真实" if luck > -0.25 else "低于预期"))
        chunk = f"{name}{tag}（运气 {luck:+.2f}/场"
        if xgd is not None and pts is not None and pos:
            chunk += f"，{pts}分第{pos}、xGD {xgd:+.1f}"
        chunk += "）"
        bits.append(chunk)
    text = "；".join(bits) + "。" if bits else "缺少 xG，无法判断积分成色。"
    if inflated:
        text += f"{inflated}积分好于底层数据，纸面排名不可全信。"
    return {"lean": lean, "title": title, "text": text, "home": hs, "away": aws}


def _quarter(x: float) -> float:
    return round(float(x) * 4) / 4


def _ah_label(std: Optional[float]) -> str:
    if std is None:
        return "无亚盘"
    q = _quarter(std)
    if abs(q) < 0.01:
        return "平手"
    side = "主让" if q < 0 else "主受让"
    v = abs(q)
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return f"{side}{s}"


def _parse_form(form) -> List[int]:
    out: List[int] = []
    buf = ""
    for ch in str(form or ""):
        if ch.isdigit():
            buf += ch
        elif buf:
            out.append(int(buf))
            buf = ""
    if buf:
        out.append(int(buf))
    return out


def _form_attack(form) -> Optional[int]:
    """本场阵型有多攻。三中卫/两前锋/四后卫三前锋偏攻，五后卫/单前锋偏守。"""
    parts = _parse_form(form)
    if len(parts) < 2:
        return None
    backs, fwds = parts[0], parts[-1]
    s = 42 + (4 - backs) * 11 + fwds * 10
    if len(parts) >= 4 and 1 <= parts[-2] <= 3:
        s += parts[-2] * 5
    if backs == 3 and sum(parts[1:-1]) >= 4:
        s += 6
    return max(18, min(88, int(round(s))))


def _xi_attack(cards: List[Dict]) -> Optional[int]:
    xi = [c for c in (cards or []) if c.get("inXi")]
    if len(xi) < 8:
        return None
    nd = sum(1 for c in xi if c.get("pos") == "D")
    nf = sum(1 for c in xi if c.get("pos") == "F")
    return max(18, min(88, int(round(42 + (4 - nd) * 11 + nf * 10))))


def _coach_attack(mgr: Optional[Dict]) -> Tuple[Optional[int], List[str]]:
    if not mgr:
        return None, []
    profile = (mgr.get("tactical_profile") or "").lower()
    zh = {"attacking": "进攻型", "defensive": "防守型", "possession": "控球型", "balanced": "均衡型"}
    base = {"attacking": 68, "possession": 58, "balanced": 50, "defensive": 32}.get(profile, 50)
    bits = []
    if profile in zh:
        bits.append(zh[profile])
    gf, ga = _f(mgr.get("avg_goals_scored")), _f(mgr.get("avg_goals_conceded"))
    if gf is not None and ga is not None:
        base += max(-12.0, min(12.0, (gf - ga) * 10))
        bits.append(f"场均{gf:.1f}/{ga:.1f}")
    poss = _f(mgr.get("avg_possession"))
    if poss is not None:
        base += max(-8.0, min(10.0, (poss - 50) * 0.4))
        bits.append(f"控球{poss:.0f}%")
    o25 = _f(mgr.get("over_25_pct"))
    if o25 is not None:
        base += (o25 - 50) * 0.15
    cs = _f(mgr.get("clean_sheet_pct"))
    if cs is not None:
        base -= (cs - 30) * 0.12
    return _pct(base), bits


def _style_side(pack: Dict, cards: List[Dict], mgr: Optional[Dict]) -> Tuple[int, str, str]:
    form = pack.get("formation")
    fs = _form_attack(form)
    if fs is None:
        fs = _xi_attack(cards)
    cs, cbits = _coach_attack(mgr)
    parts: List[Tuple[float, float]] = []
    if fs is not None:
        parts.append((float(fs), 0.62))
    if cs is not None:
        parts.append((float(cs), 0.38))
    if not parts:
        return 50, "未知", "缺少阵型/教练"
    score = int(round(sum(v * w for v, w in parts) / sum(w for _, w in parts)))
    if score >= 64:
        label = "偏攻"
    elif score <= 40:
        label = "偏守"
    else:
        label = "均衡"
    bits = []
    if form:
        bits.append(str(form))
    pref = (mgr or {}).get("preferred_formation")
    if form and pref and str(form) != str(pref):
        pf = _form_attack(pref)
        if fs is not None and pf is not None and fs <= pf - 5:
            bits.append(f"惯用{pref}，本场更收")
        elif fs is not None and pf is not None and fs >= pf + 5:
            bits.append(f"惯用{pref}，本场更攻")
        else:
            bits.append(f"惯用{pref}")
    bits.extend(cbits[:3])
    return score, label, "，".join(bits) or label


def _style_compare(h: Tuple[int, str, str], a: Tuple[int, str, str], hn: str, an: str) -> Dict[str, Any]:
    hs, hl, ht = h
    aws, al, at = a
    if hs >= 64 and aws >= 64:
        title = "对攻"
    elif hs <= 40 and aws <= 40:
        title = "互守"
    else:
        title = f"{hl} / {al}"
    if abs(hs - aws) < 10:
        lean = "even"
    elif hs > aws:
        lean = "home"
    else:
        lean = "away"
    text = f"{hn}{hl}（{hs}），{an}{al}（{aws}）。{hn}：{ht}。{an}：{at}。"
    if title == "对攻":
        text += "两边都偏攻，场面容易开。"
    elif title == "互守":
        text += "两边都收着打，进球期望看模型。"
    return {"lean": lean, "title": title, "text": text, "home": hs, "away": aws, "hLabel": hl, "aLabel": al}
    eg = ((pred or {}).get("markets") or {}).get("expected_goals") or {}
    ph, pa = _f(eg.get("home")), _f(eg.get("away"))
    if ph is None or pa is None:
        return None
    return pa - ph, ph, pa


def _xg_gd_away(pred: Optional[Dict]) -> Optional[Tuple[float, float, float]]:
    eg = ((pred or {}).get("markets") or {}).get("expected_goals") or {}
    ph, pa = _f(eg.get("home")), _f(eg.get("away"))
    if ph is None or pa is None:
        return None
    return pa - ph, ph, pa


def _ability_gd_away(raw_h: Optional[int], raw_a: Optional[int], is_neutral: bool) -> Optional[float]:
    if raw_h is None or raw_a is None:
        return None
    ha = 0.0 if is_neutral else HOME_ADV_GOALS
    raw = (raw_a - raw_h) / ABILITY_PTS_PER_GOAL - ha
    return max(-2.0, min(2.0, raw))


def _line_compare(
    raw_h: Optional[int],
    raw_a: Optional[int],
    pred: Optional[Dict],
    handicap_std: Optional[float],
    hn: str,
    an: str,
    ah_home_odds: Optional[float] = None,
    ah_away_odds: Optional[float] = None,
    is_neutral: bool = False,
) -> Optional[Dict[str, Any]]:
    if handicap_std is None:
        return None
    market_away = float(handicap_std)
    xg_pack = _xg_gd_away(pred)
    src = "模型"
    if xg_pack:
        paper_away, ph, pa = xg_pack
    else:
        paper_away = _ability_gd_away(raw_h, raw_a, is_neutral)
        ph = pa = None
        src = "能力折算"
    if paper_away is None:
        return {
            "lean": "even",
            "title": _ah_label(handicap_std),
            "text": f"盘口 {_ah_label(handicap_std)}，缺少模型对照。",
            "home": 50,
            "away": 50,
        }

    # shift>0：盘口比纸面更看主
    shift = paper_away - market_away
    hs = _pct(50 + shift * 40)
    aws = _pct(50 - shift * 40)
    paper_lbl = _ah_label(paper_away)
    mkt_lbl = _ah_label(market_away)
    same_dir = paper_away * market_away > 0 or abs(paper_away) < 0.12 or abs(market_away) < 0.12
    lean = "even"
    if abs(shift) < 0.37:
        title = "盘口贴纸面"
    elif not same_dir:
        title = "盘口和模型反向"
        lean = "home" if market_away < 0 else "away"
    elif abs(market_away) > abs(paper_away) + 0.12:
        title = "盘口深于纸面"
        lean = "home" if market_away < 0 else "away"
    else:
        title = "盘口浅于纸面"
        lean = "home" if paper_away > 0 else "away"

    if src == "模型":
        text = f"模型约{paper_lbl}（xG {ph:.2f}-{pa:.2f}），盘口{mkt_lbl}"
    else:
        text = f"能力折算约{paper_lbl}（{ABILITY_PTS_PER_GOAL:.0f}分≈1球、主场{HOME_ADV_GOALS}），盘口{mkt_lbl}"
    delta = abs(abs(market_away) - abs(paper_away)) if same_dir else abs(shift)
    if title == "盘口贴纸面":
        text += "，和模型基本一致"
    elif title == "盘口和模型反向":
        text += f"。模型{paper_lbl}，盘口走到{mkt_lbl}"
    elif title == "盘口深于纸面":
        fav = hn if market_away < 0 else an
        text += f"，比模型深 {delta:.2f} 球，更看好{fav}"
    else:
        fav = hn if paper_away < 0 else an
        text += f"，比模型浅 {delta:.2f} 球，不买{fav}那么深"
    text += "。"
    if ah_home_odds and ah_away_odds:
        if market_away > 0 and ah_home_odds < ah_away_odds:
            text += "终盘下水在下盘。"
        elif market_away < 0 and ah_away_odds < ah_home_odds:
            text += "终盘下水在下盘。"
        elif market_away > 0 and ah_away_odds < ah_home_odds:
            text += "终盘下水在上盘。"
        elif market_away < 0 and ah_home_odds < ah_away_odds:
            text += "终盘下水在上盘。"
    return {"lean": lean, "title": title, "text": text, "home": hs, "away": aws}


_ZONE_ZH = {
    "rel": "降级区",
    "relq": "降级附加赛区",
    "cl": "欧冠区",
    "ucl": "欧冠区",
    "clq": "欧冠资格赛区",
    "el": "欧联区",
    "uecl": "协会杯区",
}
_ZONE_FIGHT = {
    "rel": 28, "relq": 22,
    "cl": 18, "ucl": 18, "clq": 14,
    "el": 10, "uecl": 8,
}
_CNY = {"2026-02-16", "2026-02-17", "2026-02-18", "2027-02-05", "2027-02-06", "2027-02-07"}


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def _zone_key(stand: Any) -> Optional[str]:
    if not stand:
        return None
    z = stand.get("zone") if isinstance(stand, dict) else None
    if isinstance(z, dict):
        return z.get("key")
    return z


def _holiday_bit(kickoff: Optional[str]) -> Tuple[int, str]:
    ko = _parse_iso(kickoff)
    if not ko:
        return 0, ""
    md = (ko.month, ko.day)
    if md in {(12, 24), (12, 25), (12, 26), (12, 31), (1, 1)}:
        return -6, "圣诞/跨年赛程，轮换风险高于战意"
    if ko.date().isoformat() in _CNY:
        return -6, "春节赛程，轮换风险高于战意"
    return 0, ""


def _league_results(
    fixtures: List[Dict],
    team_id: Optional[int],
    kickoff: Optional[str],
    this_id: Any,
    league_id: Any,
) -> List[Tuple[datetime, str, bool]]:
    """联赛已完赛，不含本场。返回 (时间, WDL, 是否主场)，时间正序。"""
    if not team_id:
        return []
    ko = _parse_iso(kickoff)
    out: List[Tuple[datetime, str, bool]] = []
    for r in fixtures or []:
        if this_id is not None and r.get("id") == this_id:
            continue
        if league_id is not None and r.get("league_id") != league_id:
            continue
        hs, aws = r.get("home_score"), r.get("away_score")
        if hs is None or aws is None:
            continue
        hid, aid = r.get("home_team_id"), r.get("away_team_id")
        if team_id not in (hid, aid):
            continue
        dt = _parse_iso(r.get("event_date"))
        if not dt:
            continue
        if ko and dt >= ko - timedelta(hours=2):
            continue
        home = hid == team_id
        gf, ga = (hs, aws) if home else (aws, hs)
        res = "W" if gf > ga else ("D" if gf == ga else "L")
        out.append((dt, res, home))
    out.sort(key=lambda x: x[0])
    return out


def _form_stake(results: List[Tuple[datetime, str, bool]], is_home: bool) -> Tuple[int, str]:
    """本场利害：主场不胜/连败加分；客队正势减分（可接受一分）。"""
    recent = [r[1] for r in results[-5:]]
    if not recent:
        return 0, ""
    newest = "".join(reversed(recent))
    consec = 0
    for ch in newest:
        if ch != "L":
            break
        consec += 1
    home_games = [r for r in results if r[2]]
    home_winless = is_home and len(home_games) >= 2 and all(r[1] != "W" for r in home_games)

    if is_home:
        if home_winless:
            return 12, "主场不胜，这场不能再丢"
        if consec >= 3:
            return 14, f"近况连败{consec}场，主场要止血"
        if newest[:5].count("L") >= 3:
            return 10, "近5场败仗偏多"
        if "W" not in recent[-4:] and len(recent) >= 4:
            return 10, "近况不胜，主场刚需"
        return 0, ""

    if recent[-5:].count("W") >= 3:
        return -6, "客队近况正势，本场可接受一分"
    if consec >= 3:
        return 6, f"客队连败{consec}场"
    return 0, ""


def _pts_tension(stand: Optional[Dict], table: List[Dict], *, europe: bool) -> Tuple[int, str]:
    if not stand or not table:
        return 0, ""
    pts = _i(stand.get("pts"))
    zone = _zone_key(stand)
    pos = stand.get("position")
    ranked = sorted(
        [r for r in table if r.get("pts") is not None],
        key=lambda r: (_i(r.get("position")) or 99),
    )
    if not ranked:
        return 0, ""

    def zkey(r):
        return _zone_key(r)

    if europe and zone in ("cl", "ucl", "clq"):
        outside = [r for r in ranked if zkey(r) not in ("cl", "ucl", "clq")]
        if outside:
            gap = pts - _i(outside[0].get("pts"))
            if 0 <= gap <= 2:
                return 10, f"欧冠区领先仅{gap}分，掉出去就没了"
    if europe and zone in ("el", "uecl"):
        worse = [r for r in ranked if zkey(r) not in ("cl", "ucl", "clq", "el", "uecl")]
        if worse:
            gap = pts - _i(worse[0].get("pts"))
            if 0 <= gap <= 2:
                return 8, f"欧战区领先仅{gap}分"
    if zone not in ("rel", "relq"):
        rel_rows = [r for r in ranked if zkey(r) in ("rel", "relq")]
        if rel_rows:
            top_rel = min(_i(r.get("pts")) for r in rel_rows)
            gap = pts - top_rel
            if 0 <= gap <= 2:
                return 12, f"距降级区{gap}分"
    if zone in ("rel", "relq") and pos:
        safety = [r for r in ranked if zkey(r) not in ("rel", "relq")]
        if safety:
            gap = _i(safety[-1].get("pts")) - pts
            if 0 <= gap <= 3:
                return 8, f"距安全区{gap}分"
    return 0, ""


def _split_attention(
    fixtures: List[Dict],
    kickoff: Optional[str],
    league_id: Any,
    this_id: Any,
) -> Tuple[int, str]:
    ko = _parse_iso(kickoff)
    if not ko or not league_id:
        return 0, ""
    hi = ko + timedelta(days=4)
    for r in fixtures or []:
        if this_id is not None and r.get("id") == this_id:
            continue
        dt = _parse_iso(r.get("event_date"))
        if not dt or not (ko < dt <= hi):
            continue
        other = r.get("league_id")
        if other and other != league_id:
            return -8, "4天内另有杯赛/欧战，本场可能分心"
        break
    return 0, ""


def _euro_hangover_for_team(
    fixtures: List[Dict],
    team_id: Optional[int],
    kickoff: Optional[str],
    league_id: Any,
    this_id: Any,
) -> Tuple[int, str]:
    ko = _parse_iso(kickoff)
    if not ko or not league_id or not team_id:
        return 0, ""
    lo = ko - timedelta(days=14)
    last = None
    for r in fixtures or []:
        if this_id is not None and r.get("id") == this_id:
            continue
        other = r.get("league_id")
        if not other or other == league_id:
            continue
        hid, aid = r.get("home_team_id"), r.get("away_team_id")
        if team_id not in (hid, aid):
            continue
        dt = _parse_iso(r.get("event_date"))
        if not dt or not (lo <= dt < ko - timedelta(hours=3)):
            continue
        if last is None or dt > last[0]:
            last = (dt, r)
    if not last:
        return 0, ""
    r = last[1]
    hs, aws = r.get("home_score"), r.get("away_score")
    if hs is None or aws is None:
        return -6, "近14天有欧战/杯赛"
    hid = r.get("home_team_id")
    gf, ga = (hs, aws) if hid == team_id else (aws, hs)
    if gf < ga:
        return -10, "近14天欧战/杯赛失利，联赛战意存疑"
    return -6, "近14天有欧战/杯赛"


def _cup_stage(event: Dict) -> Tuple[int, str]:
    stage = f"{event.get('stage') or ''} {event.get('stage_name') or ''} {event.get('round_label') or ''}".lower()
    if event.get("previous_leg_event_id"):
        return 12, "两回合对决"
    keys = ("knock", "playoff", "play-off", "final", "semi", "quarter", "cup")
    if any(k in stage for k in keys) and "regular" not in stage:
        return 18, "杯赛/淘汰赛"
    return 0, ""


def _motivation(
    pack: Dict,
    *,
    is_home: bool,
    derby: bool,
    congest: int,
    event: Dict,
    opp: Dict,
    fixtures: List[Dict],
    table: List[Dict],
    team_id: Optional[int],
) -> Tuple[str, str, int]:
    bits: List[str] = []
    score = 8
    st = pack.get("stand") or {}
    zone = st.get("zone")
    pos = st.get("position")
    rnd = _i(event.get("round_number")) or _i(st.get("played"))
    early = 0 < rnd <= 8
    mid = 8 < rnd < 20
    late = rnd >= 32 or _i(st.get("played")) >= 30
    this_id = event.get("id")
    league_id = event.get("league_id")
    kickoff = event.get("event_date")

    fight = _ZONE_FIGHT.get(zone or "", 0)
    if pos and pos <= 3 and fight < 16 and not early:
        fight = max(fight, 14)
        bits.append("榜眼前列")
    if fight:
        label = _ZONE_ZH.get(zone or "", "积分利害")
        if early and zone not in ("rel", "relq"):
            fight = 0
        elif early:
            bits.append(f"处{label}，拿分刚需")
        elif mid and zone not in ("rel", "relq"):
            fight = round(fight * 0.55)
            bits.append(f"{label}（赛季中段）")
        else:
            bits.append(f"处{label}，拿分刚需" if zone in ("rel", "relq") else f"{label}，排名不能掉")
        if late and fight:
            fight = round(fight * 1.2)
            bits.append("赛季末段")
        score += fight

    ts, tb = _pts_tension(st if st.get("pts") is not None else None, table, europe=not early)
    if not ts and table and st.get("position"):
        raw = next((r for r in table if r.get("team_id") == team_id), None)
        ts, tb = _pts_tension(raw, table, europe=not early)
    if ts:
        score += ts
        bits.append(tb)

    results = _league_results(fixtures, team_id, kickoff, this_id, league_id)
    fs, fb = _form_stake(results, is_home)
    if fs:
        if derby and fs < 0:
            pass
        else:
            score += fs
            bits.append(fb)

    if derby:
        score += 16 + (4 if is_home else 0)
        bits.append("德比" + ("主场" if is_home else "") + "，战意拉满")
    elif is_home and not event.get("is_neutral_ground"):
        score += 8
        if "主场" not in (fb or ""):
            bits.append("主场")

    cs, cb = _cup_stage(event)
    if cs:
        score += cs
        bits.append(cb)

    oz = (opp.get("stand") or {}).get("zone")
    op = (opp.get("stand") or {}).get("position")
    if zone in ("rel", "relq") and oz in ("rel", "relq"):
        score += 12
        bits.append("保级直接对话")
    elif zone in ("cl", "ucl", "clq") and oz in ("cl", "ucl", "clq") and pos and op and abs(pos - op) <= 3 and not early:
        score += 8
        bits.append("欧战区近身")

    if congest >= 2:
        if derby:
            bits.append(f"近一周已打{congest}场，体能看轮换条")
        else:
            score -= 6
            bits.append(f"近一周已打{congest}场，体能可能让位于轮换")

    ss, sb = _split_attention(fixtures, kickoff, league_id, this_id)
    if ss and not derby:
        score += ss
        bits.append(sb)

    es, eb = _euro_hangover_for_team(fixtures, team_id, kickoff, league_id, this_id)
    if es:
        if derby:
            bits.append("近14天有欧战/杯赛，体能看轮换条")
        else:
            score += es
            bits.append(eb)

    hs, hb = _holiday_bit(kickoff)
    if hs and not derby:
        score += hs
        bits.append(hb)

    if late and fight <= 0 and ts <= 0 and not derby and cs <= 0:
        score -= 8
        bits.append("积分已无利害，战意存疑")

    km = _f(event.get("travel_distance_km"))
    if (not is_home) and km and km >= 800 and not derby:
        score -= 4 if km < 1500 else 6
        bits.append(f"客队行程{km:.0f}km")

    if derby:
        score = max(score, 24 if is_home else 22)

    score = max(0, min(100, score))
    if score >= 22:
        level = "高"
    elif score >= 10:
        level = "中"
    else:
        level = "低"
    if not bits:
        bits.append("联赛常规轮次")
    return level, "；".join(bits), score


def _congestion(fixtures: List[Dict], team_id: Optional[int], kickoff: Optional[str]) -> int:
    if not kickoff or not team_id:
        return 0
    try:
        ko = datetime.fromisoformat(str(kickoff).replace("Z", "+00:00"))
    except ValueError:
        return 0
    n = 0
    lo = ko - timedelta(days=7)
    for r in fixtures or []:
        if str(r.get("id") or "") == "":
            continue
        ds = r.get("event_date")
        if not ds:
            continue
        try:
            dt = datetime.fromisoformat(str(ds).replace("Z", "+00:00"))
        except ValueError:
            continue
        if lo <= dt < ko - timedelta(hours=3):
            st = (r.get("status") or "").lower()
            if st in ("finished", "closed", "complete", "completed", "scheduled", "fixture"):
                n += 1
    return n


def relevant_player_ids(
    home_lu: Dict,
    away_lu: Dict,
    unav: Dict,
    recent: Dict,
    cap: int = 28,
) -> List[int]:
    ids: List[int] = []
    seen = set()

    def add(pid):
        if pid is None:
            return
        i = int(pid)
        if i in seen:
            return
        seen.add(i)
        ids.append(i)

    for p in _xi(home_lu) + _xi(away_lu):
        add(p.get("id"))
    for side in ("home", "away"):
        cnt, n = _start_counts(recent.get(side) or [])
        for pid, c in cnt.items():
            if n >= 3 and c >= 3:
                add(pid)
        block = unav.get(side) if isinstance(unav, dict) else None
        for p in block or []:
            add(p.get("id"))
    return ids[:cap]


def build_assessment(
    *,
    home_name: str,
    away_name: str,
    event: Dict,
    home_lu: Dict,
    away_lu: Dict,
    unav: Dict,
    recent: Dict,
    standings: Any,
    fixtures: Dict,
    profiles: Dict[int, Dict],
    stats: Dict[int, List[Dict]],
    prediction: Optional[Dict],
    home_team_id: Optional[int],
    away_team_id: Optional[int],
    handicap_std: Optional[float] = None,
    ah_home_odds: Optional[float] = None,
    ah_away_odds: Optional[float] = None,
    managers: Optional[Dict] = None,
) -> Dict[str, Any]:
    eid = event.get("id")
    h_cnt, h_n = _start_counts(recent.get("home") or [], exclude_id=eid)
    a_cnt, a_n = _start_counts(recent.get("away") or [], exclude_id=eid)
    h_last = _recent_blocks(recent.get("home") or [], exclude_id=eid)
    a_last = _recent_blocks(recent.get("away") or [], exclude_id=eid)
    h_last_ids = _xi_ids((h_last[-1].get("lineups") or {}).get(h_last[-1].get("side"))) if h_last else []
    a_last_ids = _xi_ids((a_last[-1].get("lineups") or {}).get(a_last[-1].get("side"))) if a_last else []

    h_xi_ids = set(_xi_ids(home_lu))
    a_xi_ids = set(_xi_ids(away_lu))
    eid = event.get("id")

    unav_h = unav.get("home") if isinstance(unav, dict) else []
    unav_a = unav.get("away") if isinstance(unav, dict) else []
    injured_ids = set()
    for p in (unav_h or []) + (unav_a or []):
        if p.get("id") is not None:
            injured_ids.add(int(p["id"]))

    def cards_for(xi_block, cnt, n_cols, team_id, xi_ids):
        by = {}
        for p in _xi(xi_block):
            pid = p.get("id")
            if pid is None:
                continue
            by[int(pid)] = p
        extra = []
        for pid, c in cnt.items():
            if pid in by:
                continue
            if n_cols >= 3 and c >= 3:
                extra.append({"id": pid, "name": (profiles.get(pid) or {}).get("short_name") or str(pid),
                              "position": (profiles.get(pid) or {}).get("position")})
        out = []
        for p in _xi(xi_block) + extra:
            pid = p.get("id")
            if pid is None:
                continue
            pid = int(pid)
            out.append(_player_card(
                p, team_id=team_id, starts=cnt.get(pid, 0), n_cols=n_cols,
                in_xi=pid in xi_ids, profile=profiles.get(pid),
                stats_rows=stats.get(pid) or [], exclude_event=eid,
                injured=pid in injured_ids,
            ))
        xi_keep = [c for c in out if c.get("inXi")]
        rest = [c for c in out if not c.get("inXi")]
        rest.sort(key=lambda c: (
            POS_ORDER.get(c.get("pos") or "", 9),
            -(c.get("profileRating") or 0),
            -(c.get("xg") or 0),
        ))
        return xi_keep + rest

    h_cards = cards_for(home_lu, h_cnt, h_n, home_team_id, h_xi_ids)
    a_cards = cards_for(away_lu, a_cnt, a_n, away_team_id, a_xi_ids)

    h_dropped = [c for c in h_cards if (not c.get("inXi")) and c.get("role") == "主力"]
    a_dropped = [c for c in a_cards if (not c.get("inXi")) and c.get("role") == "主力"]

    h_stand = _stand_row(standings, home_team_id, event.get("home_team"))
    a_stand = _stand_row(standings, away_team_id, event.get("away_team"))

    h_pack = _side_pack(home_name, home_lu, h_cards, h_last_ids, h_n, h_stand, unav_h or [], h_dropped)
    a_pack = _side_pack(away_name, away_lu, a_cards, a_last_ids, a_n, a_stand, unav_a or [], a_dropped)
    h_pack["droppedNames"] = [c.get("name") for c in h_dropped]
    a_pack["droppedNames"] = [c.get("name") for c in a_dropped]

    hc, hl, ht = _completeness(h_pack, h_cards)
    ac, al, at = _completeness(a_pack, a_cards)
    hrot, hrl, hrt = _rotation(h_pack, h_cards)
    arot, arl, art = _rotation(a_pack, a_cards)
    mgrs = managers or {}
    hst = _style_side(h_pack, h_cards, mgrs.get("home") if isinstance(mgrs, dict) else None)
    ast = _style_side(a_pack, a_cards, mgrs.get("away") if isinstance(mgrs, dict) else None)
    h_pack["styleLabel"] = hst[1]
    a_pack["styleLabel"] = ast[1]
    style = _style_compare(hst, ast, home_name, away_name)
    ab = _ability_compare(
        h_pack, a_pack, home_name, away_name, event.get("league_id"),
        is_neutral=bool(event.get("is_neutral_ground")),
    )
    xg = _xg_compare(h_pack, a_pack, prediction, home_name, away_name)
    over = _overperf_compare(h_pack, a_pack, home_name, away_name)
    line = _line_compare(
        ab.get("home"), ab.get("away"), prediction, handicap_std,
        home_name, away_name, ah_home_odds, ah_away_odds,
        is_neutral=bool(event.get("is_neutral_ground")),
    )
    derby = bool(event.get("is_local_derby"))
    table = _rows_as_list(standings)
    hcong = _congestion(fixtures.get("home") or [], home_team_id, event.get("event_date"))
    acong = _congestion(fixtures.get("away") or [], away_team_id, event.get("event_date"))
    hml, hmt, hms = _motivation(
        h_pack, is_home=True, derby=derby, congest=hcong, event=event, opp=a_pack,
        fixtures=fixtures.get("home") or [], table=table, team_id=home_team_id,
    )
    aml, amt, ams = _motivation(
        a_pack, is_home=False, derby=derby, congest=acong, event=event, opp=h_pack,
        fixtures=fixtures.get("away") or [], table=table, team_id=away_team_id,
    )
    mgrs = managers or {}
    hst = _style_side(h_pack, h_cards, mgrs.get("home") if isinstance(mgrs, dict) else None)
    ast = _style_side(a_pack, a_cards, mgrs.get("away") if isinstance(mgrs, dict) else None)
    h_pack["styleLabel"] = hst[1]
    a_pack["styleLabel"] = ast[1]
    style = _style_compare(hst, ast, home_name, away_name)

    verdicts = [
        {"key": "ability", "label": "能力", "lean": ab["lean"], "title": ab["title"],
         "home": ab.get("home"), "away": ab.get("away"), "text": ab["text"]},
        {"key": "completeness", "label": "完整度",
         "lean": "home" if hc >= ac + 12 else ("away" if ac >= hc + 12 else "even"),
         "title": f"{hl} / {al}",
         "home": hc, "away": ac,
         "text": (
             f"{home_name}{hl}（{hc}），{away_name}{al}（{ac}）。"
             + (f"{home_name}：{ht}。" if ht and ht != "近况主力齐" else "")
             + (f"{away_name}：{at}。" if at and at != "近况主力齐" else "")
             + ("两边近况主力齐。" if (not ht or ht == "近况主力齐") and (not at or at == "近况主力齐") else "")
         )},
        {"key": "style", "label": "攻势", "lean": style["lean"], "title": style["title"],
         "home": style.get("home"), "away": style.get("away"), "text": style["text"]},
        {"key": "xg", "label": "进球期望", "lean": xg["lean"], "title": xg["title"],
         "home": xg.get("home"), "away": xg.get("away"), "text": xg["text"]},
        *([{
            "key": "overperf", "label": "虚高", "lean": over["lean"], "title": over["title"],
            "home": over.get("home"), "away": over.get("away"), "text": over["text"],
        }] if over else []),
        {"key": "motivation", "label": "战意",
         "lean": "home" if hms >= ams + 8 else ("away" if ams >= hms + 8 else "even"),
         "title": f"{hml} / {aml}",
         "home": hms, "away": ams,
         "text": f"{home_name}{hml}（{hms}），{away_name}{aml}（{ams}）。{hmt}。{amt}。"},
        {"key": "rotation", "label": "轮换",
         "lean": "home" if arot >= hrot + 15 else ("away" if hrot >= arot + 15 else "even"),
         "title": f"{hrl} / {arl}",
         "home": hrot, "away": arot,
         "text": (
             f"{home_name}{hrl}（{hrot}），{away_name}{arl}（{arot}）。"
             f"{home_name}{hrt}。{away_name}{art}。"
         )},
        *([{
            "key": "line", "label": "盘口", "lean": line["lean"], "title": line["title"],
            "home": line.get("home"), "away": line.get("away"), "text": line["text"],
        }] if line else []),
    ]

    facts = []
    for c in h_dropped:
        facts.append({"text": f"{home_name} 近况主力未发 {_name(c) if False else c.get('name')}", "tone": "warn"})
    for c in a_dropped:
        facts.append({"text": f"{away_name} 近况主力未发 {c.get('name')}", "tone": "warn"})
    if unav_h:
        facts.append({"text": f"{home_name}伤停 {len(unav_h)} 人", "tone": "warn" if len(unav_h) >= 3 else ""})
    if unav_a:
        facts.append({"text": f"{away_name}伤停 {len(unav_a)} 人", "tone": "warn" if len(unav_a) >= 3 else ""})
    if hcong >= 2:
        facts.append({"text": f"{home_name}近 7 天已有 {hcong} 场", "tone": ""})
    if acong >= 2:
        facts.append({"text": f"{away_name}近 7 天已有 {acong} 场", "tone": ""})

    return {
        "verdicts": verdicts,
        "facts": facts,
        "sides": {"home": h_pack, "away": a_pack},
        "players": {"home": h_cards, "away": a_cards},
    }
