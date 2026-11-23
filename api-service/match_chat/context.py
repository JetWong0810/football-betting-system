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


TICK_COMPANIES = {
    "asian": [(22, "Pinnacle"), (3, "皇冠"), (7, "澳门")],
    "ou": [(22, "Pinnacle"), (3, "皇冠"), (2, "Bet365")],
    "euro": [(0, "平均欧赔"), (2, "Bet365")],
}


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
    """其余公司(皇冠/澳门/Pinnacle 等)的逐次变动关键路径。无数据返回空串。"""
    from zgzcw_cache import list_ah_ticks, list_ou_ticks, list_euro_ticks
    fetch = {"asian": lambda c: list_ah_ticks(match_id, cid=c), "ou": lambda c: list_ou_ticks(match_id, c),
             "euro": lambda c: list_euro_ticks(match_id, c)}
    title = {"asian": "亚盘", "ou": "大小球", "euro": "欧赔(胜/平/负,隐含概率已去水)"}
    out: List[str] = []
    total = 0
    for kind in ("asian", "ou", "euro"):
        for cid, name in TICK_COMPANIES[kind]:
            if kind == "asian" and cid == 2:
                continue
            rows = fetch[kind](cid)
            if len(rows) < 2:      # 仅1条等于没有变动
                continue
            asc = list(reversed(rows))
            pick = compress_ticks(kind, asc)
            total += len(rows)
            out.append(f"{name} {title[kind]} 逐次变动(共{len(rows)}次,仅列关键变动点,从早到晚):")
            out.extend(f"- {t.get('time')} {_tick_row(kind, t)}" for t in pick)
    if not out:
        return "", 0
    return "\n【其他公司逐次变动】\n" + "\n".join(out), total


def render_market(match_id: str, match: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """多家公司亚盘 / 欧赔 / 大小球 + Bet365 亚盘逐次变动。只读缓存,无联网。竞彩赔率口径不同,不纳入。"""
    from zgzcw_cache import get_fenxi_cache, list_ah_ticks, load_predict_inputs, _companies
    cache = get_fenxi_cache(match_id) or {}
    _, asian, euro = load_predict_inputs(match)
    euro_c = [x for x in ((euro or {}).get("companies") or []) if x.get("bookmaker") != "竞彩官方"]
    ou_c = _companies(cache.get("ou_json"))
    ticks = list_ah_ticks(match_id, cid=2)
    n = {"asian": len(asian or []), "euro": len(euro_c), "ou": len(ou_c), "ticks": len(ticks)}
    L: List[str] = []

    def ts(k):
        from zgzcw_cache import fmt_cst
        v = fmt_cst(cache.get(k))
        return f",抓取于 {v[5:16]}(北京时间)" if v else ""

    L.append(f"\n【盘口】亚盘·多家公司初盘→即时盘{ts('asian_fetched_at')}。盘口用文字表示:主让=主队让球,主受让=主队受让;水位为主队水/客队水。")
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
                 f"主水{_w(i.get('home'), cu.get('home'))} 客水{_w(i.get('away'), cu.get('away'))}")
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
        L.append(f"\n【大小球】多家公司初盘→即时盘(大球水/小球水){ts('ou_fetched_at')}")
        for o in ou_c:
            i, cu = o.get("initial") or {}, o.get("current") or {}
            L.append(f"- {o.get('bookmaker')}: {i.get('line')}→{cu.get('line')} | 大水{_w(i.get('over'), cu.get('over'))} 小水{_w(i.get('under'), cu.get('under'))}")
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


_HEAD_KEY = (("比赛", "id"), ("盘口", "odds"), ("欧赔", "odds"), ("大小球", "odds"), ("历史同赔", "f6"), ("七因子", "pred"), ("公众号文章", "arts"),
             ("交锋历史", "h2h"), ("主队近期战绩", "recent"), ("客队近期战绩", "recent"), ("未来赛程", "recent"))
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
