"""北单(非竞彩)场次的聊天上下文: 比赛信息 + 盘口赔率(复用 render_market) + 交锋/近期战绩/未来赛事/积分。
没有历史同赔、七因子预测、关联文章。只读库, 不联网; 抓取由 service.run_turn 在用户要求时触发。"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Dict, List, Tuple

import bd_service

from .context import MatchNotFound, _form_stats, render_market, split_sections

CUT_NOTE = "盘口列为该行主队视角的文字盘口(主让=主队让球, 受=主队受让), 与本系统亚盘口径不一定一致, 不要据此判断历史让球方。"


def _rows_text(rows: List[Dict[str, Any]]) -> List[str]:
    out = []
    for r in rows:
        ht = f" | 半场{r['half']}" if r.get("half") else ""
        hc = f" | 盘口{r['handicapText']}" if r.get("handicapText") else ""
        wt = f"(水位{r['ahWater']})" if r.get("ahWater") else ""
        ar = f" | 盘路{r['ahResult']}" if r.get("ahResult") else ""
        ou = f" | {r['ou']}球" if r.get("ou") in ("大", "小") else ""
        out.append(f"{r['date']} {r['competition']} {r['home']} {r['score']} {r['away']}{ht}{hc}{wt} | {r.get('result') or ''}{ar}{ou}")
    return out


def _stats(rows: List[Dict[str, Any]], team: str) -> str:
    conv = [{"result": r.get("result"), "match": f"{r['home']} {r['score'].replace('-', ':')} {r['away']}"} for r in rows]
    return _form_stats(conv, team)


def _standing(side: Dict[str, List[str]], rank: str, name: str) -> str:
    cols = "比赛/胜/平/负/进/失/净/积分/排名/胜率"
    parts = [f"{k} {'/'.join(v)}" for k, v in (side or {}).items()]
    return f"{name}{rank}: " + "; ".join(parts) if parts else ""


def render_fenxi(m: Dict[str, Any], data: Dict[str, Any], at: datetime) -> Tuple[str, Dict[str, int]]:
    ht, at_n = m["homeTeam"], m["awayTeam"]
    cutoff = (m.get("kickoff") or "9999-99-99")[:10]
    before = lambda rows: [r for r in (rows or []) if str(r.get("date") or "") < cutoff]
    h2h, hr, ar = before(data.get("h2h")), before(data.get("homeRecent")), before(data.get("awayRecent"))
    stamp = f"(数据来自 500.com 数据页, 抓取于 {at.strftime('%m-%d %H:%M')} 北京时间)" if at else ""
    L: List[str] = []
    L.append(f"\n【交锋历史】{ht}(本场主队)视角,共 {len(h2h)} 场{stamp};最近{min(10, len(h2h))}场: {_stats(h2h[:10], ht)}")
    L.append("说明: " + CUT_NOTE)
    L.extend(_rows_text(h2h[:10]) or ["(无交锋记录)"])
    for tag, name, rows in (("主队", ht, hr), ("客队", at_n, ar)):
        L.append(f"\n【{tag}近期战绩】{name},该队视角,最近 {min(10, len(rows))} 场: {_stats(rows[:10], name)}")
        L.extend(_rows_text(rows[:10]) or ["(无记录)"])
    st = data.get("standings") or {}
    sl = [x for x in (_standing(st.get("home"), st.get("homeRank", ""), ht), _standing(st.get("away"), st.get("awayRank", ""), at_n)) if x]
    if sl:
        L.append("\n【赛前联赛积分】(每组列: 比赛/胜/平/负/进/失/净/积分/排名/胜率)")
        L.extend(sl)
    fut = []
    for tag, rows in (("主队", data.get("homeFuture")), ("客队", data.get("awayFuture"))):
        rs = [f"{r['date']} {r['competition']} {r['home']}VS{r['away']}({r.get('gap') or ''})" for r in (rows or []) if str(r.get("date") or "") >= cutoff][:4]
        if rs:
            fut.append(f"{tag}: " + "; ".join(rs))
    if fut:
        L.append("\n【未来赛程】(赛程密度/轮换参考)")
        L.extend(fut)
    try:
        from .schedule import schedule_text
        st = schedule_text(cutoff, ht, at_n, hr, ar, data.get("homeFuture"), data.get("awayFuture"))
        if st:
            L.append(st)
    except Exception:  # noqa: BLE001  赛程密度算不出来不影响其余内容
        pass
    return "\n".join(L), {"h2h": len(h2h), "home": len(hr), "away": len(ar)}


def build_bd_context(match_id: str) -> Dict[str, Any]:
    m = bd_service.get_match(match_id)
    if not m:
        raise MatchNotFound(match_id)
    ht, at_n = m["homeTeam"], m["awayTeam"]
    head = [f"【比赛】", f"{m['league']} | 主 {ht} vs 客 {at_n} | 开赛 {m['kickoff']} | 北单期号 {m['period']} 第{m['num']}场(非竞彩场次)"
            + (f" | 北单让球 {m['rq']}" if m.get("rq") else "") + (f" | 500.com 亚盘让球 {m['ahText']}" if m.get("ahText") else "")]
    if m.get("score"):
        head.append(f"已完赛: 比分 {m['score'].replace(':', '-')}")
    mk = {"asian": 0, "euro": 0, "ou": 0, "ticks": 0}
    market = ""
    try:
        fake = {"match_id": match_id, "home_team_name": ht, "away_team_name": at_n, "match_timestamp": m["kickoffTs"]}
        market, mk = render_market(match_id, fake)
    except Exception:  # noqa: BLE001
        market = ""
    if not market.strip() or (not mk["asian"] and not mk["euro"] and not mk["ou"]):
        market = ("\n【盘口】本场盘口赔率尚未抓取。北单场次不做定时抓取,需要用户说"
                  "\"抓取本场最新的盘口赔率数据\"才会实时抓取并存库。")
    form, fn = "", {"h2h": 0, "home": 0, "away": 0}
    data, at = bd_service.load_fenxi(match_id)
    if data:
        form, fn = render_fenxi(m, data, at)
    else:
        form = ("\n【交锋历史】本场交锋/近期战绩/未来赛程尚未抓取。需要用户说\"请关联本场交锋和近期战绩\"才会实时抓取。")
    text = "\n".join(head) + market + form
    summary = {"bd": True, "asian": mk["asian"], "euro": mk["euro"], "ou": mk["ou"], "ticks": mk["ticks"],
               "h2h": fn["h2h"], "homeRecent": fn["home"], "awayRecent": fn["away"],
               "fenxiAt": at.strftime("%m-%d %H:%M") if at else None, "f6": 0, "articles": 0, "prediction": False}
    return {"item": None, "prediction": None, "text": text, "summary": summary, "sections": split_sections(text),
            "hash": hashlib.sha1(text.encode()).hexdigest()[:16], "snap": mk.get("snap"), "home": ht, "away": at_n}
