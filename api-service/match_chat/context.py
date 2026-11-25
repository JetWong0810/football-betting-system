"""单场「系统数据」上下文:盘口 + 历史同赔(F6) + 已存七因子预测。只读,不调用任何模型。"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from database import get_db


CST = timezone(timedelta(hours=8))


class MatchNotFound(Exception):
    pass


def _wilson(k: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    if n <= 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (c - m) / d), min(1.0, (c + m) / d)


def _sale_date(match_number: str) -> Optional[str]:
    s = str(match_number or "")
    if len(s) >= 6 and s[:6].isdigit():
        return f"20{s[0:2]}-{s[2:4]}-{s[4:6]}"
    return None


def _load_match_row(match_id: str) -> Dict[str, Any]:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT match_id, match_number, home_score, away_score FROM matches WHERE match_id=%s", (match_id,))
        row = cur.fetchone()
    if not row:
        raise MatchNotFound(match_id)
    return row


def _load_item(match_id: str, row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """复用批量同赔接口的单场结果,保证与页面所见一致。"""
    import main as _main  # 延迟导入,避免循环依赖

    date = _sale_date(row.get("match_number"))
    if not date:
        return None
    status = "finished" if row.get("home_score") is not None else "not_started"
    res = _main.batch_similar(date=date, status=status)
    for it in res.get("items") or []:
        if str(it.get("matchId")) == str(match_id):
            return it
    return None


def _load_prediction(match_id: str) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT direction, confidence, overall_reverse, handicap, factors_json, analysis, predicted_at "
            "FROM prediction_history WHERE match_id=%s", (match_id,))
        r = cur.fetchone()
    if not r:
        return None
    try:
        factors = json.loads(r.get("factors_json") or "[]")
    except json.JSONDecodeError:
        factors = []
    return {"direction": r["direction"], "confidence": r["confidence"],
            "overallReverse": bool(r["overall_reverse"]),
            "handicap": float(r["handicap"]) if r.get("handicap") is not None else None,
            "factors": factors, "analysis": r.get("analysis") or "",
            "predictedAt": r["predicted_at"].strftime("%Y-%m-%d %H:%M") if r.get("predicted_at") else None}


DIR_CN = {"upper": "上盘", "lower": "下盘", "neutral": "中性"}


def _fmt_ah(v: Optional[float]) -> str:
    if v is None:
        return "无"
    return f"{v:+g}" if v else "0"


def _odds3(o: Optional[Dict[str, Any]]) -> str:
    if not o:
        return "无"
    return f"{o.get('win')}/{o.get('draw')}/{o.get('lose')}"


def _f6_stats(f6: Dict[str, Any]) -> Dict[str, Any]:
    up = lo = 0
    for m in f6.get("matches") or []:
        r = m.get("ahResult")
        if r in ("上盘", "半上"):
            up += 1
        elif r in ("下盘", "半下"):
            lo += 1
    n = up + lo
    lead, k = ("upper", up) if up >= lo else ("lower", lo)
    lo_ci, hi_ci = _wilson(k, n)
    return {"upper": up, "lower": lo, "decided": n, "lead": lead,
            "leadPct": round(k * 100 / n, 1) if n else 0,
            "ci": [round(lo_ci * 100), round(hi_ci * 100)]}


def _load_full_match(match_id: str) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM matches WHERE match_id=%s", (match_id,))
        return cur.fetchone()


def _score_of(txt: str) -> Optional[Tuple[str, int, int, str]]:
    m = re.match(r"^(.*?)(\d+)\s*[:：]\s*(\d+)(.*)$", (txt or "").strip())
    return (m.group(1).strip(), int(m.group(2)), int(m.group(3)), m.group(4).strip()) if m else None


def _rows_before(rows: List[Dict[str, Any]], cutoff: str) -> List[Dict[str, Any]]:
    return [r for r in (rows or []) if str(r.get("date") or "") < cutoff]


def _form_stats(rows: List[Dict[str, Any]], team: str) -> str:
    w = d = l = gf = ga = n = 0
    for r in rows:
        res = r.get("result")
        w += res == "胜"
        d += res == "平"
        l += res == "负"
        sc = _score_of(r.get("match") or "")
        if sc and team:
            left, a, b, right = sc
            if team[:2] in left:
                gf += a; ga += b; n += 1
            elif team[:2] in right:
                gf += b; ga += a; n += 1
    s = f"{w}胜{d}平{l}负"
    if n:
        s += f",场均进{gf / n:.1f}失{ga / n:.1f}"
    return s


def _rows_text(rows: List[Dict[str, Any]], with_hc: bool = True) -> List[str]:
    out = []
    for r in rows:
        hc = f" | 盘口{r.get('handicap')}" if with_hc and r.get("handicap") not in (None, "") else ""
        ht = f" | 半场{r.get('halfScore')}" if r.get("halfScore") else ""
        out.append(f"{r.get('date')} {r.get('competition')} {r.get('match')}{ht}{hc} | {r.get('result') or ''}")
    return out


def render_form(match: Dict[str, Any], form: Optional[Dict[str, Any]], n_h2h: int = 10, n_rec: int = 10) -> Tuple[str, Dict[str, Any]]:
    """交锋历史 / 双方近期战绩 / 未来赛程(只读缓存,无联网)。已完赛场次只取开赛日之前的记录。"""
    if not form:
        return "\n【交锋/近期战绩】暂无数据。", {"h2h": 0, "home": 0, "away": 0}
    ht, at = match.get("home_team_name") or "主队", match.get("away_team_name") or "客队"
    ts = match.get("match_timestamp")
    cutoff = datetime.fromtimestamp(int(ts), CST).strftime("%Y-%m-%d") if ts else "9999-99-99"
    h2h = _rows_before(form.get("h2h"), cutoff)
    hr = _rows_before(form.get("homeRecent"), cutoff)
    ar = _rows_before(form.get("awayRecent"), cutoff)
    L: List[str] = []
    rk = f"(联赛排名 {form.get('homeRank')} / {form.get('awayRank')})" if form.get("homeRank") or form.get("awayRank") else ""
    L.append(f"\n【交锋历史】{ht}(本场主队)视角,共 {len(h2h)} 场,列最近 {min(n_h2h, len(h2h))} 场;"
             f"最近{min(n_h2h, len(h2h))}场: {_form_stats(h2h[:n_h2h], ht)} {rk}")
    L.append("说明: 盘口为数据源原值,方向符号不保证与本系统亚盘口径一致,不要据此判断历史让球方。")
    L.extend(_rows_text(h2h[:n_h2h]) or ["(无交锋记录)"])
    for tag, name, rows in (("主队", ht, hr), ("客队", at, ar)):
        L.append(f"\n【{tag}近期战绩】{name},该队视角,最近 {min(n_rec, len(rows))} 场: {_form_stats(rows[:n_rec], name)}")
        L.extend(_rows_text(rows[:n_rec]) or ["(无记录)"])
    fut = []
    for tag, rows in (("主队", form.get("homeFuture")), ("客队", form.get("awayFuture"))):
        rs = [f"{r.get('date')} {r.get('competition')} {r.get('match')}" for r in (rows or []) if str(r.get("date") or "") >= cutoff][:3]
        if rs:
            fut.append(f"{tag}: " + "; ".join(rs))
    if fut:
        L.append("\n【未来赛程】(赛程密度/轮换参考)")
        L.extend(fut)
    return "\n".join(L), {"h2h": len(h2h), "home": len(hr), "away": len(ar)}


def _ah_txt(h: Optional[float], text: str = "") -> str:
    """数据源原值: 正=主让, 负=主受让。输出用文字避免符号歧义。"""
    if h is None:
        return "-"
    t = f"({text})" if text else ""
    if h == 0:
        return "平手" + t
    return (f"主让{abs(h):g}" if h > 0 else f"主受让{abs(h):g}") + t


def _w(a, b) -> str:
    f = lambda v: "-" if v is None else f"{v:g}"
    return f"{f(a)}→{f(b)}"


def _probs(o: Optional[Dict[str, Any]]) -> Optional[Tuple[float, float, float]]:
    try:
        w, d, l = float(o["win"]), float(o["draw"]), float(o["lose"])
        s = 1 / w + 1 / d + 1 / l
        return 100 / w / s, 100 / d / s, 100 / l / s
    except (TypeError, KeyError, ValueError, ZeroDivisionError):
        return None


# 逐次变动展示的公司(按关注度排序)。zcid 为足彩网 cid(500.com 无数据时兜底); 香港马会足彩网无
TICK_COMPANIES = [
    ("香港马会", None), ("Bet365", 2), ("Pinnacle", 22), ("皇冠", 3), ("澳门", 7),
    ("威廉希尔", 9), ("立博", 5), ("伟德", None), ("易胜博", None), ("利记", None), ("明陞", None),
]
_CORE_NAMES = {"香港马会", "Bet365", "Pinnacle", "皇冠", "澳门", "威廉希尔", "立博"}


def compress_ticks(kind: str, asc: List[Dict[str, Any]], cap: int = 12) -> List[Dict[str, Any]]:
    """逐次变动压缩(时间从早到晚输入)。保留: 首条、盘口线变化点(欧赔为隐含概率累计变化>=1pp)、最后一条;
    超过 cap 时保留首条+最近 cap-1 条,避免上下文膨胀。"""
    if len(asc) <= 2:
        return list(asc)
    keep = [asc[0]]
    for t in asc[1:-1]:
        last = keep[-1]
        if kind == "asian":
            hit = t.get("handicap") != last.get("handicap")
        elif kind == "ou":
            hit = t.get("line") != last.get("line")
        else:
            a, b = _probs(last), _probs(t)
            hit = bool(a and b and max(abs(b[i] - a[i]) for i in range(3)) >= 1.0)
        if hit:
            keep.append(t)
    keep.append(asc[-1])
    if len(keep) > cap:
        keep = [keep[0]] + keep[-(cap - 1):]
    return keep


def _tick_row(kind: str, t: Dict[str, Any]) -> str:
    if kind == "asian":
        return f"{_ah_txt(t.get('handicap'), t.get('handicapText'))} 主水{t.get('home')} 客水{t.get('away')}"
    if kind == "ou":
        return f"{t.get('line')} 大水{t.get('over')} 小水{t.get('under')}"
    pr = _probs(t)
    ip = f" 隐含 {pr[0]:.1f}/{pr[1]:.1f}/{pr[2]:.1f}" if pr else ""
    return f"{t.get('win')}/{t.get('draw')}/{t.get('lose')}{ip}"


def render_tick_paths(match_id: str) -> Tuple[str, int]:
    """多家公司亚盘/大小球/欧赔逐次变动的关键路径。500.com 来源优先, 无数据回退足彩网。Bet365 亚盘另有专段。"""
    from zgzcw_cache import list_ah_ticks, list_ou_ticks, list_euro_ticks, list_o500_ticks
    fb = {"asian": list_ah_ticks, "ou": list_ou_ticks, "euro": list_euro_ticks}
    k500 = {"asian": "asian", "ou": "overunder", "euro": "european"}
    title = {"asian": "亚盘", "ou": "大小球", "euro": "欧赔(胜/平/负,隐含概率已去水)"}
    out: List[str] = []
    total = 0
    for kind in ("asian", "ou", "euro"):
        for name, zcid in TICK_COMPANIES:
            if kind == "asian" and name == "Bet365":
                continue
            rows = list_o500_ticks(k500[kind], match_id, name)
            src = "500.com"
            if not rows and zcid is not None:
                rows = fb[kind](match_id, zcid) if kind != "asian" else list_ah_ticks(match_id, cid=zcid)
                src = "足彩网"
            if len(rows) < 2:      # 仅1条等于没有变动
                continue
            asc = list(reversed(rows))
            pick = compress_ticks(kind, asc, cap=10 if name in _CORE_NAMES else 6)
            total += len(rows)
            out.append(f"{name} {title[kind]} 逐次变动(来源{src},共{len(rows)}次,最新 {asc[-1].get('time')},仅列关键变动点,从早到晚):")
            out.extend(f"- {t.get('time')} {_tick_row(kind, t)}" for t in pick)
    if not out:
        return "", 0
    return "\n【其他公司逐次变动】(时间均为北京时间; 开赛后的滚球记录已剔除)\n" + "\n".join(out), total


_BJ = timezone(timedelta(hours=8))


def _utc_to_bj(d):
    return d.replace(tzinfo=timezone.utc).astimezone(_BJ).replace(tzinfo=None) if d else None


_KIND_T500 = {"asian": "odds500_ah_ticks", "ou": "odds500_ou_ticks", "euro": "odds500_euro_ticks"}
_KIND_CN = {"asian": "亚盘", "ou": "大小球", "euro": "欧赔"}
_KIND_ZG = {"asian": ("asian_fetched_at", "ticks_fetched_at"), "ou": ("ou_fetched_at",), "euro": ("euro_fetched_at",)}


def market_freshness(match_id: str, now: Optional[datetime] = None) -> Dict[str, Any]:
    """盘口赔率数据新鲜度, 分亚盘/大小球/欧赔三类各自计算(大小球曾因排在抓取末位而长期偏旧, 不能被亚盘的新鲜度掩盖)。
    每类 lastFetch=最近一次成功抓取(北京时间, 取 500.com 与足彩网中较新者); ageMin=三类里最旧的那类的滞后分钟数
    (任一类从未抓到则为 None)。lastChange=最近一条变动记录(盘口平静时变动会很旧, 但数据仍是新的)。"""
    now = now or datetime.now(_BJ).replace(tzinfo=None)
    out: Dict[str, Any] = {"now": now, "eta": None, "lastFetch": None, "lastChange": None, "ageMin": None, "kinds": {}}
    kinds: Dict[str, List[datetime]] = {k: [] for k in _KIND_T500}
    changes = []
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT match_timestamp FROM matches WHERE match_id=%s", (match_id,))
            r = cur.fetchone()
            if not r and str(match_id).startswith("bd_"):
                cur.execute("SELECT kickoff_ts AS match_timestamp FROM bd_matches WHERE match_id=%s", (match_id,))
                r = cur.fetchone()
            if r and r.get("match_timestamp"):
                out["eta"] = float(r["match_timestamp"]) - now.replace(tzinfo=_BJ).timestamp()
            for k, t in _KIND_T500.items():
                try:
                    cur.execute(f"SELECT MAX(fetched_at) f, MAX(tick_time) c FROM {t} WHERE match_id=%s", (match_id,))
                    x = cur.fetchone() or {}
                    if x.get("f"):
                        kinds[k].append(_utc_to_bj(x["f"]))
                    if x.get("c"):
                        changes.append(x["c"])
                except Exception:  # noqa: BLE001  表尚未创建
                    pass
            for t in ("jczq_ah_ticks", "jczq_ou_ticks", "jczq_euro_ticks"):
                try:
                    cur.execute(f"SELECT MAX(tick_time) c FROM {t} WHERE match_id=%s", (match_id,))
                    x = cur.fetchone() or {}
                    if x.get("c"):
                        changes.append(x["c"])
                except Exception:  # noqa: BLE001
                    pass
            cur.execute("SELECT asian_fetched_at, euro_fetched_at, ou_fetched_at, ticks_fetched_at "
                        "FROM jczq_fenxi_cache WHERE match_id=%s", (match_id,))
            x = cur.fetchone() or {}
            for k, cols in _KIND_ZG.items():
                for col in cols:
                    if x.get(col):
                        kinds[k].append(_utc_to_bj(x[col]))
    except Exception:  # noqa: BLE001
        return out
    ages = []
    for k, vals in kinds.items():
        last = max(vals) if vals else None
        age = max(0, int((now - last).total_seconds() // 60)) if last else None
        out["kinds"][k] = {"lastFetch": last, "ageMin": age}
        ages.append(age)
    fetched = [v["lastFetch"] for v in out["kinds"].values() if v["lastFetch"]]
    if fetched:
        out["lastFetch"] = max(fetched)
    if ages and all(a is not None for a in ages):
        out["ageMin"] = max(ages)           # 最旧的一类
    elif fetched:
        out["ageMin"] = None                # 有的类别从未抓到
    if changes:
        out["lastChange"] = max(changes)
    return out


def _fmt_eta(eta: Optional[float]) -> str:
    if eta is None:
        return "开赛时间未知"
    if eta <= 0:
        return f"已开赛 {int(-eta // 60)} 分钟"
    return f"距开赛 {int(eta // 3600)} 小时 {int(eta % 3600 // 60)} 分钟" if eta >= 3600 else f"距开赛 {int(eta // 60)} 分钟"


def freshness_text(fr: Dict[str, Any]) -> str:
    s = f"数据新鲜度: 当前北京时间 {fr['now'].strftime('%m-%d %H:%M')},{_fmt_eta(fr['eta'])}。"
    kinds = fr.get("kinds") or {}
    parts = []
    for k in ("asian", "ou", "euro"):
        v = kinds.get(k) or {}
        parts.append(f"{_KIND_CN[k]} {v['lastFetch'].strftime('%H:%M')}({v['ageMin']} 分钟前)" if v.get("lastFetch") else f"{_KIND_CN[k]} 无抓取记录")
    s += "各类盘口最近一次成功抓取:" + "、".join(parts) if kinds else "盘口赔率没有成功抓取记录"
    if fr["lastChange"]:
        s += f";最近一条变动记录发生在 {fr['lastChange'].strftime('%m-%d %H:%M')}(盘口平静时变动记录会很旧,不代表数据旧)"
    s += "。"
    eta = fr["eta"]
    stale = [_KIND_CN[k] for k in ("asian", "ou", "euro")
             if (kinds.get(k) or {}).get("ageMin") is None or kinds[k]["ageMin"] > 10]
    if eta is not None and 0 < eta <= 3 * 3600 and stale:
        s += (f"【注意】临近开赛,{'、'.join(stale)}的数据已滞后(见上),之后的盘口变动这份数据里没有。"
              "分析时必须先说明这一点,涉及这几类的结论要标注'数据可能不是最新',不得断言市场已经消化了某条消息(如首发),"
              "也不得把'抓取时间'当作'盘口变动时间';用户可以说\"抓取本场最新的盘口赔率\"来刷新。")
    return s


def _halves(line: float) -> List[float]:
    return [line - 0.25, line + 0.25] if abs(line * 4) % 2 == 1 else [line]


def _res_word(adjs: List[float]) -> str:
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


def ah_reading(h_raw: Optional[float], home: str, away: str) -> str:
    """亚盘读法。h_raw 为数据源原值(正=主让)。给出各净胜球下上盘/下盘的结算, 避免模型现推时说反。"""
    if h_raw is None:
        return ""
    if h_raw == 0:
        up_side, line_txt = None, "平手盘"
    else:
        up_side = home if h_raw > 0 else away
        line_txt = f"{'主让' if h_raw > 0 else '主受让'}{abs(h_raw):g}"
    parts = []
    for d, name in ((2, f"{home}净胜2球及以上"), (1, f"{home}赢1球"), (0, "平局"), (-1, f"{away}赢1球"), (-2, f"{away}净胜2球及以上")):
        home_res = _res_word([d - x for x in _halves(h_raw)])
        away_res = {"全赢": "全输", "全输": "全赢", "赢半": "输半", "输半": "赢半", "走水": "走水"}[home_res]
        parts.append(f"{name}→{home}{home_res}/{away}{away_res}")
    head = f"当前主流亚盘 {line_txt}"
    if up_side:
        down = away if up_side == home else home
        head += f":上盘=让球方({up_side}),下盘=受让方({down})"
    return head + "。结算(以主队盘口计): " + "; ".join(parts) + "。"


def ou_reading(line: Optional[float]) -> str:
    if line is None:
        return ""
    parts = []
    for t in sorted({max(0, int(line) - 1), max(0, int(line)), int(line) + 1, int(line) + 2}):
        big = _res_word([t - x for x in _halves(line)])
        small = {"全赢": "全输", "全输": "全赢", "赢半": "输半", "输半": "赢半", "走水": "走水"}[big]
        parts.append(f"总进球{t}→大球{big}/小球{small}")
    return f"当前主流大小球 {line:g}: " + "; ".join(parts) + "。"


_P_GRID = (0.50, 0.52, 0.55, 0.58, 0.60)


def breakeven_text(label_a: str, w_a, label_b: str, w_b) -> str:
    """盈亏平衡水位: 有效胜率 p(赢半按 0.5 计入)下, 港式水位 w 至少为 (1-p)/p 才不亏。并对照当前两边水位。"""
    row = "/".join(f"{round(p * 100)}%→{(1 - p) / p:.2f}" for p in _P_GRID)
    cur = []
    for lab, w in ((label_a, w_a), (label_b, w_b)):
        try:
            cur.append(f"{lab}{float(w):.2f}(需有效胜率≥{100 / (1 + float(w)):.1f}%)")
        except (TypeError, ValueError):
            pass
    tail = f";Bet365 当前水位 {' '.join(cur)}" if cur else ""
    return f"有效胜率→所需最低港式水位(简化估算): {row}{tail}"


def _novig(a: Optional[float], b: Optional[float]) -> str:
    """港式水位(净赔率)两边去水概率。"""
    try:
        pa, pb = 1 / (1 + float(a)), 1 / (1 + float(b))
        return f"{pa / (pa + pb) * 100:.1f}% / {pb / (pa + pb) * 100:.1f}%"
    except (TypeError, ValueError, ZeroDivisionError):
        return ""


_NAME_ALIAS = {"伟德": "韦德"}          # 500.com 叫伟德, 足彩网叫韦德(同一家)
_FIELDS = {
    "asian": lambda t: {"home": t.get("home"), "handicap": t.get("handicap"), "handicapText": t.get("handicapText"), "away": t.get("away")},
    "ou": lambda t: {"over": t.get("over"), "line": t.get("line"), "under": t.get("under")},
    "euro": lambda t: {"win": t.get("win"), "draw": t.get("draw"), "lose": t.get("lose")},
}
_K500 = {"asian": "asian", "ou": "overunder", "euro": "european"}


def overlay_500(match_id: str, kind: str, cache_items: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    """把 500.com 逐次变动折成"初盘→即时盘"并覆盖/补充快照(最早一条=初盘, 最新一条=即时盘)。
    足彩网快照的大小球排在抓取末位, 常比 500.com 旧几十分钟; 500.com 有数据就以它为准, 没有的公司保留快照。
    返回 (合并后的列表, 被 500.com 覆盖或新增的公司数)。"""
    from odds500_ticks import COMPANIES
    from zgzcw_cache import list_o500_ticks
    out = [dict(x) for x in cache_items]
    by_name = {x.get("bookmaker"): i for i, x in enumerate(out)}
    used = 0
    for cid, name in COMPANIES.items():
        rows = list_o500_ticks(_K500[kind], match_id, name)
        if not rows:
            continue
        cn = _NAME_ALIAS.get(name, name)
        item = {"bookmaker": cn, "initial": _FIELDS[kind](rows[-1]), "current": _FIELDS[kind](rows[0]),
                "src500": True, "asof": rows[0].get("time")}
        if kind == "euro":
            item["returnRate"] = rows[0].get("returnRate")
        if cn in by_name:
            old = out[by_name[cn]]
            for k in ("cid", "raw_name"):
                if k in old:
                    item[k] = old[k]
            out[by_name[cn]] = item
        else:
            by_name[cn] = len(out)
            out.append(item)
        used += 1
    return out, used


def _odd_open(kind: str, i: Dict[str, Any]) -> str:
    """初盘水位明显失衡(源数据如此, 500.com 与足彩网一致)时给出标注, 避免被误判为抓取错误或当成有效初盘。"""
    ws = [i.get(k) for k in {"asian": ("home", "away"), "ou": ("over", "under"), "euro": ()}[kind]]
    try:
        if any(w is not None and (float(w) < 0.6 or float(w) > 1.3) for w in ws):
            return " ⚠初盘水位失衡(源数据如此,非抓取错误),不宜作为有效初盘参考"
    except (TypeError, ValueError):
        pass
    return ""


def render_market(match_id: str, match: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """多家公司亚盘 / 欧赔 / 大小球 + Bet365 亚盘逐次变动。只读缓存,无联网。竞彩赔率口径不同,不纳入。"""
    from zgzcw_cache import get_fenxi_cache, list_ah_ticks, load_predict_inputs, _companies
    cache = get_fenxi_cache(match_id) or {}
    _, asian, euro = load_predict_inputs(match)
    euro_c = [x for x in ((euro or {}).get("companies") or []) if x.get("bookmaker") != "竞彩官方"]
    ou_c = _companies(cache.get("ou_json"))
    from zgzcw_cache import list_o500_ticks
    ov: Dict[str, int] = {}
    try:
        asian, ov["asian"] = overlay_500(match_id, "asian", list(asian or []))
        ou_c, ov["ou"] = overlay_500(match_id, "ou", ou_c)
        euro_c, ov["euro"] = overlay_500(match_id, "euro", euro_c)
    except Exception:  # noqa: BLE001  500.com 数据不可用时沿用足彩网快照
        pass
    ticks = list_o500_ticks("asian", match_id, "Bet365") or list_ah_ticks(match_id, cid=2)
    n = {"asian": len(asian or []), "euro": len(euro_c), "ou": len(ou_c), "ticks": len(ticks)}
    L: List[str] = []

    def ts(k):
        from zgzcw_cache import fmt_cst
        v = fmt_cst(cache.get(k))
        return f",抓取于 {v[5:16]}(北京时间)" if v else ""

    L.append(f"\n【盘口】亚盘·多家公司初盘→即时盘{ts('asian_fetched_at')}"
             + (f";其中 {ov.get('asian')} 家来自 500.com 实时抓取(以其「最新变动」时间为准)" if ov.get("asian") else "")
             + "。盘口用文字表示:主让=主队让球,主受让=主队受让;水位为主队水/客队水。")
    try:
        L.append(freshness_text(market_freshness(match_id)))
    except Exception:  # noqa: BLE001  新鲜度失败不影响其余内容
        pass
    # 盘口读法: 当前主流盘(优先 Bet365 最新变动), 预先算好结算与去水概率, 不让模型现推上下盘/赢半输半
    try:
        from zgzcw_cache import list_ou_ticks as _lou
        home_n, away_n = (match or {}).get("home_team_name") or "主队", (match or {}).get("away_team_name") or "客队"
        h_now = ticks[0].get("handicap") if ticks else None
        w_h = (ticks[0].get("home"), ticks[0].get("away")) if ticks else (None, None)
        if h_now is None:
            b = next((a for a in (asian or []) if a.get("bookmaker") == "Bet365"), None)
            if b:
                cu = b.get("current") or {}
                h_now, w_h = cu.get("handicap"), (cu.get("home"), cu.get("away"))
        r1 = ah_reading(h_now, home_n, away_n)
        if r1:
            nv = _novig(*w_h)
            L.append("【盘口读法】" + r1 + (f"(Bet365 最新水位去水后 主队/客队覆盖概率 {nv})" if nv else ""))
            L.append("【水位参考·亚盘】" + breakeven_text(f"{home_n}水", w_h[0], f"{away_n}水", w_h[1]))
        ot = list_o500_ticks("overunder", match_id, "Bet365") or _lou(match_id, 2)
        o_line, o_w = (ot[0].get("line"), (ot[0].get("over"), ot[0].get("under"))) if ot else (None, (None, None))
        if o_line is None:
            b = next((o for o in ou_c if o.get("bookmaker") == "Bet365"), None)
            if b:
                cu = b.get("current") or {}
                o_line, o_w = cu.get("line"), (cu.get("over"), cu.get("under"))
        r2 = ou_reading(o_line)
        if r2:
            nv = _novig(*o_w)
            L.append(r2 + (f"(Bet365 最新水位去水后 大球/小球概率 {nv})" if nv else ""))
            L.append("【水位参考·大小球】" + breakeven_text("大球水", o_w[0], "小球水", o_w[1]))
    except Exception:  # noqa: BLE001
        pass
    up = down = same = 0
    for a in asian or []:
        i, cu = a.get("initial") or {}, a.get("current") or {}
        hi, hc = i.get("handicap"), cu.get("handicap")
        if hi is None or hc is None:
            mv = "无法比较"
        elif hc > hi:
            mv, up = "升盘(主队更被看好)", up + 1
        elif hc < hi:
            mv, down = "降盘(主队热度下降)", down + 1
        else:
            mv, same = "盘口不变", same + 1
        L.append(f"- {a.get('bookmaker')}: {_ah_txt(hi, i.get('handicapText'))}→{_ah_txt(hc, cu.get('handicapText'))} | {mv} | "
                 f"主水{_w(i.get('home'), cu.get('home'))} 客水{_w(i.get('away'), cu.get('away'))}"
                 + (f" | 最新变动 {str(a.get('asof'))[5:16]}" if a.get("src500") else " | 来源足彩网快照") + _odd_open("asian", i))
    if asian:
        L.append(f"汇总: {len(asian)}家公司中 升盘{up} 降盘{down} 不变{same}")
    else:
        L.append("(暂无亚盘抓取数据)")

    if ticks:
        asc = list(reversed(ticks))
        pick = asc if len(asc) <= 11 else [asc[0]] + asc[-10:]
        L.append(f"\nBet365 亚盘逐次变动(共{len(ticks)}次,时间从早到晚" + (",首条为最早记录,其后为最近10次" if len(asc) > 11 else "") + "):")
        prev = None
        for t in pick:
            tag = "" if prev is None else (" 升盘" if (t.get("handicap") or 0) > (prev or 0) else (" 降盘" if (t.get("handicap") or 0) < (prev or 0) else ""))
            L.append(f"- {t.get('time')} {_ah_txt(t.get('handicap'), t.get('handicapText'))} 主水{t.get('home')} 客水{t.get('away')}{tag}")
            prev = t.get("handicap")

    L.append(f"\n【欧赔】多家公司初赔→即时赔率(胜/平/负){ts('euro_fetched_at')}。已排除竞彩官方(竞彩让球与赔率口径不同)。隐含概率已去除返还率。")
    sw = sd = sl = 0.0
    k = 0
    for e in euro_c:
        i, cu = e.get("initial") or {}, e.get("current") or {}
        pi, pc = _probs(i), _probs(cu)
        ch = ""
        if pi and pc:
            d = [pc[x] - pi[x] for x in range(3)]
            ch = f" | 隐含概率 胜{pi[0]:.1f}→{pc[0]:.1f} 平{pi[1]:.1f}→{pc[1]:.1f} 负{pi[2]:.1f}→{pc[2]:.1f}"
            sw, sd, sl, k = sw + d[0], sd + d[1], sl + d[2], k + 1
        rr = f" | 返还率{e.get('returnRate')}%" if e.get("returnRate") else ""
        L.append(f"- {e.get('bookmaker')}: 初 {i.get('win')}/{i.get('draw')}/{i.get('lose')} → 即 {cu.get('win')}/{cu.get('draw')}/{cu.get('lose')}{rr}{ch}")
    if k:
        L.append(f"汇总: {k}家公司平均隐含概率变化 胜{sw / k:+.1f}pp 平{sd / k:+.1f}pp 负{sl / k:+.1f}pp")
    elif not euro_c:
        L.append("(暂无欧赔抓取数据)")

    if ou_c:
        L.append(f"\n【大小球】多家公司初盘→即时盘(大球水/小球水){ts('ou_fetched_at')}"
                 + (f";其中 {ov.get('ou')} 家来自 500.com 实时抓取(以其「最新变动」时间为准,比足彩网快照新)" if ov.get("ou") else ""))
        for o in ou_c:
            i, cu = o.get("initial") or {}, o.get("current") or {}
            L.append(f"- {o.get('bookmaker')}: {i.get('line')}→{cu.get('line')} | 大水{_w(i.get('over'), cu.get('over'))} 小水{_w(i.get('under'), cu.get('under'))}"
                     + (f" | 最新变动 {str(o.get('asof'))[5:16]}" if o.get("src500") else " | 来源足彩网快照") + _odd_open("ou", i))
    paths, pn = render_tick_paths(match_id)
    if paths:
        L.append(paths)
        n["ticks"] += pn
    return "\n".join(L), n


def render_text(it: Dict[str, Any], pred: Optional[Dict[str, Any]], arts: Optional[List[Dict[str, Any]]] = None) -> str:
    L: List[str] = []
    ht, at = it["homeTeam"]["name"], it["awayTeam"]["name"]
    L.append("【比赛】")
    L.append(f"{it.get('league')} | 主 {ht} vs 客 {at} | 开赛 {it.get('matchDate')} {it.get('matchTime')} | "
             f"期号 {it.get('matchNumber')} | {'单关' if it.get('isSingle') else '非单关'}")
    if it.get("status") == "finished" or it.get("actualScore"):
        L.append(f"已完赛: 比分 {it.get('actualScore')} ({it.get('actualResult')}), 实际盘路 {it.get('actualAh') or '无'}")

    f6 = it.get("f6") or {}
    L.append("\n【历史同赔 F6】(池为2018-2026已完赛; 匹配: 低赔方±0.03+高赔方±0.1, 同侧、变动方向一致, 剔除本场)")
    L.append(f"方向 {DIR_CN.get(f6.get('direction'), f6.get('direction'))} | 参考分 {f6.get('refScore')} "
             f"| 构成 {json.dumps(f6.get('refBreakdown'), ensure_ascii=False)} | {f6.get('reason')}")
    st = _f6_stats(f6)
    if st["decided"]:
        L.append(f"盘路统计(含半上/半下, 不含走水): 上盘 {st['upper']} / 下盘 {st['lower']}, 共 {st['decided']} 场; "
                 f"领先方 {DIR_CN[st['lead']]} {st['leadPct']}%, 95%置信区间 {st['ci'][0]}%-{st['ci'][1]}% "
                 f"(样本小时区间很宽,不可当作稳定规律)")
    ms = f6.get("matches") or []
    if ms:
        L.append(f"样本明细(前{min(12, len(ms))}/{len(ms)}场): 日期|联赛|对阵|比分|亚盘初->终|终盘赔率|盘路")
        for m in ms[:12]:
            L.append(f"{m.get('date')}|{m.get('league')}|{m.get('homeTeam')}-{m.get('awayTeam')}|{m.get('score')}|"
                     f"{m.get('handicapOpen')}->{m.get('handicapClose')}|{m.get('closeOdds')}|{m.get('ahResult')}")

    L.append("\n【七因子预测(已存结果,非实时重算)】")
    if pred:
        L.append("注意: 该预测生成于上方所示时间,此后盘口/赔率/同赔可能已变化。若与上方【盘口】【历史同赔】实时数据不一致,"
                 "以实时数据为准,并向用户指出该差异。")
        L.append(f"综合方向 {DIR_CN.get(pred['direction'], pred['direction'])} | 置信度 {pred['confidence']}% | "
                 f"整体逆向 {'是' if pred['overallReverse'] else '否'} | 预测时间 {pred['predictedAt']}")
        for f in pred["factors"]:
            L.append(f"- {f.get('name')}: 分数 {f.get('score')} | {f.get('direction') or ''} | {f.get('reason')}")
        if pred.get("analysis"):
            L.append(f"系统小结: {pred['analysis']}")
    else:
        L.append("该场尚无已存的七因子预测。")

    if arts:
        MK = {"spf": "胜平负", "rqspf": "让球胜平负", "ah": "亚盘", "ou": "大小球", "score": "比分", "dc": "双选", "other": "其他"}
        SEL = {"home": "主胜", "draw": "平", "away": "客胜", "home_draw": "主胜或平", "away_draw": "客胜或平",
               "over": "大", "under": "小"}
        VS = {"confirmed": "已证实", "contradicted": "被反驳", "unverified": "未验证"}
        L.append("\n【公众号文章】(用户订阅的公众号;内容是作者观点和二手信息,不是已核实事实;只能辅助参考)")
        for a in arts:
            tag = "赛前" if a["timing"] == "preview" else "赛后复盘"
            link = "(关联存疑)" if a["linkStatus"] == "ambiguous" else ""
            rec = (f"该号历史推荐命中率 {a['rate']}% (已结算{a['decided']}条" + ("" if a["enough"] else ",样本不足,不具参考性") + ")"
                   if a.get("rate") is not None else "该号暂无已结算推荐,命中率未知")
            L.append(f"- [{a['account']}] {a['time']} {tag}{link}《{a['title']}》; {rec}")
            if a.get("summary"):
                L.append(f"  总结: {a['summary']}")
            if a.get("body"):
                L.append(f"  正文节选(供用户针对本文提问时引用,仍是作者观点): {a['body']}")
            ST = {"strong": "强", "medium": "中", "weak": "弱"}
            for p in a["picks"]:
                kind = "作者明确表达" if p["explicit"] else "AI据文意推测(并非作者原话)"
                L.append(f"  作者倾向[{kind},强度{ST.get(p['strength'], p['strength'])}]: "
                         f"{MK.get(p['market'], p['market'])}{(' ' + str(p['line'])) if p['line'] else ''} "
                         f"{SEL.get(p['selection'], p['selection'])}; 依据: {p.get('reasoning') or '无'} (结算:{p['result']})")
            for c in a["claims"]:
                note = f" | {c['verify_note']}" if c.get("verify_note") else ""
                L.append(f"  事实声明[{VS.get(c['verify_status'], c['verify_status'])}]: {c['text']}{note}")
    return "\n".join(L)


_HEAD_KEY = (("比赛", "id"), ("盘口", "odds"), ("欧赔", "odds"), ("大小球", "odds"), ("其他公司", "odds"), ("水位参考", "odds"), ("历史同赔", "f6"), ("七因子", "pred"), ("公众号文章", "arts"),
             ("交锋历史", "h2h"), ("赛前联赛积分", "recent"), ("主队近期战绩", "recent"), ("客队近期战绩", "recent"), ("未来赛程", "recent"))
SECTION_LABEL = {"odds": "盘口赔率", "f6": "历史同赔", "pred": "七因子预测", "h2h": "交锋历史",
                 "recent": "近期战绩与赛程", "arts": "关联文章"}


def split_sections(text: str) -> Dict[str, str]:
    """按【标题】切分上下文: id(比赛标识) / odds / f6 / pred / arts / h2h / recent。"""
    out: Dict[str, List[str]] = {}
    key = None
    for line in text.split("\n"):
        if line.startswith("【"):
            head = line[1:line.index("】")] if "】" in line else line[1:]
            key = next((k for pre, k in _HEAD_KEY if head.startswith(pre)), None)
        if key:
            out.setdefault(key, []).append(line)
    return {k: "\n".join(v).strip() for k, v in out.items()}


def build_context(match_id: str) -> Dict[str, Any]:
    if str(match_id).startswith("bd_"):          # 北单(非竞彩)场次: 只有盘口赔率+交锋/战绩, 无同赔/七因子
        from .bd_context import build_bd_context
        return build_bd_context(match_id)
    row = _load_match_row(match_id)
    it = _load_item(match_id, row)
    if not it:
        raise MatchNotFound(match_id)
    pred = _load_prediction(match_id)
    try:
        from wx_articles.query import match_articles_context
        arts = match_articles_context(match_id)
    except Exception:  # 文章表不可用不影响聊天
        arts = []
    form_text, form_n = "", {"h2h": 0, "home": 0, "away": 0}
    try:
        from zgzcw_cache import load_match_form
        full = _load_full_match(match_id)
        form_text, form_n = render_form(full, load_match_form(full)) if full else ("", form_n)
    except Exception:  # noqa: BLE001  缓存不可用不影响聊天
        pass
    market_text, mk = "", {"asian": 0, "euro": 0, "ou": 0, "ticks": 0}
    try:
        full2 = _load_full_match(match_id)
        market_text, mk = render_market(match_id, full2) if full2 else ("", mk)
    except Exception:  # noqa: BLE001
        pass
    text = render_text(it, pred, arts) + market_text + form_text
    f6 = it.get("f6") or {}
    summary = {
        "asian": mk["asian"], "euro": mk["euro"], "ou": mk["ou"], "ticks": mk["ticks"],
        "f6": len(f6.get("matches") or []),
        "h2h": form_n["h2h"], "homeRecent": form_n["home"], "awayRecent": form_n["away"],
        "articles": len(arts), "prediction": bool(pred),
    }
    return {"item": it, "prediction": pred, "text": text, "summary": summary, "sections": split_sections(text),
            "hash": hashlib.sha1(text.encode()).hexdigest()[:16],
            "home": it["homeTeam"]["name"], "away": it["awayTeam"]["name"]}
