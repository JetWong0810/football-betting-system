"""单场「系统数据」上下文:盘口 + 历史同赔(F6) + 已存七因子预测。只读,不调用任何模型。"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, List, Optional, Tuple

from database import get_db


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


def render_text(it: Dict[str, Any], pred: Optional[Dict[str, Any]], arts: Optional[List[Dict[str, Any]]] = None) -> str:
    L: List[str] = []
    ht, at = it["homeTeam"]["name"], it["awayTeam"]["name"]
    L.append("【比赛】")
    L.append(f"{it.get('league')} | 主 {ht} vs 客 {at} | 开赛 {it.get('matchDate')} {it.get('matchTime')} | "
             f"期号 {it.get('matchNumber')} | {'单关' if it.get('isSingle') else '非单关'}")
    if it.get("status") == "finished" or it.get("actualScore"):
        L.append(f"已完赛: 比分 {it.get('actualScore')} ({it.get('actualResult')}), 实际盘路 {it.get('actualAh') or '无'}")

    L.append("\n【盘口】(亚盘符号: 负=主让, 正=主受让; 上盘=让球方, 下盘=受让方)")
    ao, ac = it.get("ahHandicapOpen"), it.get("ahHandicapClose")
    move = ""
    if ao is not None and ac is not None:
        move = "不变" if ao == ac else ("盘口向主队倾斜(主队更被看好)" if ac < ao else "盘口向客队倾斜(客队更被看好)")
    L.append(f"亚盘(Bet365) 初 {_fmt_ah(ao)} -> 终 {_fmt_ah(ac)} {move}")
    if it.get("handicap") is not None:
        L.append(f"竞彩让球(整数,仅参考,非亚盘): {it['handicap']:+g}")
    spf, nspf = it.get("spf"), it.get("nspf")
    for tag, o in (("竞彩胜平负(spf)", spf), ("竞彩让球胜平负(nspf)", nspf)):
        if o:
            L.append(f"{tag} 初 {_odds3(o.get('initial'))} -> 终 {_odds3(o.get('current'))} (主胜/平/客胜)")
    if it.get("beidanDeep"):
        L.append("北单让球标记: 深盘1.5")
    if it.get("beidanFlip"):
        L.append("北单让球标记: 与竞彩让球方向相反")

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
    text = render_text(it, pred, arts)
    return {"item": it, "prediction": pred, "text": text,
            "hash": hashlib.sha1(text.encode()).hexdigest()[:16],
            "home": it["homeTeam"]["name"], "away": it["awayTeam"]["name"]}
