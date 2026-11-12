"""文章列表/详情/按比赛查询(只读) + 手动关联/重新分析。"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from database import get_db

CST = timezone(timedelta(hours=8))
MAX_REPROCESS = 5


def _fmt(dt: Optional[datetime]) -> Optional[str]:
    return dt.strftime("%Y-%m-%d %H:%M") if dt else None


def _match_brief(r: Dict[str, Any]) -> Dict[str, Any]:
    ko = datetime.fromtimestamp(int(r["match_timestamp"]), CST) if r.get("match_timestamp") else None
    return {
        "matchId": r["match_id"], "code": r.get("match_code"), "league": r.get("league_name"),
        "home": r.get("home_team_name"), "away": r.get("away_team_name"),
        "kickoff": ko.strftime("%m-%d %H:%M") if ko else None,
        "score": (f"{r['home_score']}-{r['away_score']}" if r.get("home_score") is not None else None),
    }


_MATCH_COLS = ("m.match_id, m.match_code, m.league_name, m.home_team_name, m.away_team_name, "
               "m.match_timestamp, m.home_score, m.away_score")


def list_articles(link: str = "all", wxid: str = "", match_id: str = "", date: str = "",
                  page: int = 1, size: int = 20) -> Dict[str, Any]:
    where, params = ["1=1"], []
    if wxid:
        where.append("a.wxid=%s"); params.append(wxid)
    if date:
        where.append("DATE(a.publish_time)=%s"); params.append(date)
    if match_id:
        where.append("EXISTS (SELECT 1 FROM wx_article_match x WHERE x.article_id=a.id AND x.match_id=%s)")
        params.append(match_id)
    if link == "linked":
        where.append("EXISTS (SELECT 1 FROM wx_article_match x WHERE x.article_id=a.id)")
    elif link == "unlinked":
        where.append("NOT EXISTS (SELECT 1 FROM wx_article_match x WHERE x.article_id=a.id)")
    w = " AND ".join(where)
    size = max(1, min(size, 50))
    off = (max(page, 1) - 1) * size
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) n FROM wx_article a WHERE {w}", params)
        total = cur.fetchone()["n"]
        cur.execute(
            f"SELECT a.id, a.wxid, a.account_name, a.title, a.url, a.publish_time, a.status, a.summary, a.last_error "
            f"FROM wx_article a WHERE {w} ORDER BY a.publish_time DESC, a.id DESC LIMIT %s OFFSET %s",
            (*params, size, off))
        arts = list(cur.fetchall() or [])
        ids = [a["id"] for a in arts]
        by_art: Dict[int, List[Dict[str, Any]]] = {i: [] for i in ids}
        picks: Dict[int, int] = {i: 0 for i in ids}
        if ids:
            ph = ",".join(["%s"] * len(ids))
            cur.execute(
                f"SELECT x.article_id, x.timing, x.status, {_MATCH_COLS} FROM wx_article_match x "
                f"JOIN matches m ON m.match_id=x.match_id WHERE x.article_id IN ({ph}) ORDER BY m.match_timestamp",
                ids)
            for r in cur.fetchall() or []:
                b = _match_brief(r); b["timing"] = r["timing"]; b["linkStatus"] = r["status"]
                by_art[r["article_id"]].append(b)
            cur.execute(f"SELECT article_id, COUNT(*) n FROM wx_article_pick WHERE article_id IN ({ph}) GROUP BY article_id", ids)
            for r in cur.fetchall() or []:
                picks[r["article_id"]] = r["n"]
    items = [{
        "id": a["id"], "wxid": a["wxid"], "account": a["account_name"], "title": a["title"], "url": a["url"],
        "publishTime": _fmt(a["publish_time"]), "status": a["status"], "summary": a["summary"],
        "matches": by_art.get(a["id"], []), "pickCount": picks.get(a["id"], 0),
        "error": a["last_error"] if a["status"] == "failed" else None,
    } for a in arts]
    return {"total": total, "page": page, "size": size, "items": items}


def article_detail(article_id: int) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, wxid, account_name, title, url, publish_time, status, summary, last_error, attempts, "
                    "analysis_json FROM wx_article WHERE id=%s", (article_id,))
        a = cur.fetchone()
        if not a:
            return None
        cur.execute(
            f"SELECT x.timing, x.status, x.confidence, x.evidence, {_MATCH_COLS} FROM wx_article_match x "
            f"JOIN matches m ON m.match_id=x.match_id WHERE x.article_id=%s ORDER BY m.match_timestamp", (article_id,))
        ms = []
        for r in cur.fetchall() or []:
            b = _match_brief(r)
            b.update({"timing": r["timing"], "linkStatus": r["status"], "confidence": r["confidence"],
                      "evidence": r["evidence"], "claims": [], "picks": []})
            ms.append(b)
        idx = {m["matchId"]: m for m in ms}
        cur.execute("SELECT match_id, claim_type, side, subject, text, quote, verify_status, verify_note, impact_dir, "
                    "impact_level FROM wx_article_claim WHERE article_id=%s ORDER BY id", (article_id,))
        for r in cur.fetchall() or []:
            if r["match_id"] in idx:
                idx[r["match_id"]]["claims"].append({
                    "type": r["claim_type"], "side": r["side"], "subject": r["subject"], "text": r["text"],
                    "quote": r["quote"], "verify": r["verify_status"], "note": r["verify_note"],
                    "impactDir": r["impact_dir"], "impactLevel": r["impact_level"]})
        cur.execute("SELECT match_id, market, basis, line, line_source, selection, explicit, strength, reasoning, quote, result "
                    "FROM wx_article_pick WHERE article_id=%s", (article_id,))
        for r in cur.fetchall() or []:
            if r["match_id"] in idx:
                idx[r["match_id"]]["picks"].append({
                    "market": r["market"], "basis": r["basis"], "line": r["line"], "lineSource": r["line_source"],
                    "selection": r["selection"], "explicit": bool(r["explicit"]), "strength": r["strength"],
                    "reasoning": r["reasoning"], "quote": r["quote"], "result": r["result"]})
    extra = {}
    if a.get("analysis_json"):
        try:
            extra = json.loads(a["analysis_json"])
        except json.JSONDecodeError:
            extra = {}
    return {"id": a["id"], "wxid": a["wxid"], "account": a["account_name"], "title": a["title"], "url": a["url"],
            "publishTime": _fmt(a["publish_time"]), "status": a["status"], "summary": a["summary"],
            "error": a["last_error"] if a["status"] == "failed" else None, "attempts": a["attempts"],
            "matches": ms, "otherMatches": extra.get("other_matches") or [],
            "canReprocess": a["status"] == "failed" or (a["status"] == "done" and not ms)}


def accounts() -> List[Dict[str, Any]]:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT wxid, MAX(account_name) name, COUNT(*) n FROM wx_article GROUP BY wxid ORDER BY n DESC")
        return [{"wxid": r["wxid"], "name": r["name"], "count": r["n"]} for r in cur.fetchall() or []]


def match_counts(match_ids: List[str]) -> Dict[str, int]:
    if not match_ids:
        return {}
    ph = ",".join(["%s"] * len(match_ids))
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT match_id, COUNT(DISTINCT article_id) n FROM wx_article_match "
                    f"WHERE match_id IN ({ph}) GROUP BY match_id", match_ids)
        return {r["match_id"]: r["n"] for r in cur.fetchall() or []}


def link_candidates(article_id: int) -> List[Dict[str, Any]]:
    from .processor import candidates
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT publish_time FROM wx_article WHERE id=%s", (article_id,))
        r = cur.fetchone()
    if not r:
        return []
    pub = r["publish_time"] or datetime.now(CST).replace(tzinfo=None)
    return [_match_brief(c) for c in candidates(pub)]


def manual_link(article_id: int, match_id: str) -> bool:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT publish_time FROM wx_article WHERE id=%s", (article_id,))
        a = cur.fetchone()
        cur.execute("SELECT match_timestamp FROM matches WHERE match_id=%s AND match_id NOT LIKE 'jczq%%'", (match_id,))
        m = cur.fetchone()
        if not a or not m:
            return False
        ko = datetime.fromtimestamp(int(m["match_timestamp"]), CST).replace(tzinfo=None)
        pub = a["publish_time"]
        timing = "preview" if (pub and pub < ko) else "review"
        cur.execute(
            "INSERT INTO wx_article_match (article_id, match_id, timing, status, confidence, evidence) "
            "VALUES (%s,%s,%s,'manual',100,'手动关联') ON DUPLICATE KEY UPDATE status='manual', confidence=100",
            (article_id, match_id, timing))
        return True


def unlink(article_id: int, match_id: str) -> bool:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM wx_article_match WHERE article_id=%s AND match_id=%s", (article_id, match_id))
        return cur.rowcount > 0


def reprocess(article_id: int) -> str:
    """返回 ok | notfound | notallowed | limit"""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT status, attempts FROM wx_article WHERE id=%s", (article_id,))
        a = cur.fetchone()
        if not a:
            return "notfound"
        cur.execute("SELECT COUNT(*) n FROM wx_article_match WHERE article_id=%s", (article_id,))
        linked = cur.fetchone()["n"]
        if not (a["status"] == "failed" or (a["status"] == "done" and linked == 0)):
            return "notallowed"
        if a["attempts"] >= MAX_REPROCESS:
            return "limit"
        cur.execute("UPDATE wx_article SET status='pending' WHERE id=%s", (article_id,))
        return "ok"


# ---------------------------------------------------------------- 公众号命中率
MIN_SAMPLE = 30
_HIT_SIDE = ("hit", "hhit")
_DECIDED = ("hit", "hhit", "hmiss", "miss")


def _rate(rows: Dict[str, int]):
    from match_chat.context import _wilson
    decided = sum(rows.get(k, 0) for k in _DECIDED)
    hit = sum(rows.get(k, 0) for k in _HIT_SIDE)
    if not decided:
        return None, None, 0
    lo, hi = _wilson(hit, decided)
    return round(hit * 100 / decided, 1), [round(lo * 100), round(hi * 100)], decided


def account_stats() -> List[Dict[str, Any]]:
    from .processor import CST as _  # noqa: F401  (保证模块可用)
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT wxid, MAX(account_name) name, COUNT(*) n FROM wx_article GROUP BY wxid")
        accts = {r["wxid"]: {"wxid": r["wxid"], "name": r["name"], "articles": r["n"]} for r in cur.fetchall() or []}
        # 计入口径: 仅 strong/medium;weak 单列。按 (明说/推测) 分口径。
        cur.execute("SELECT wxid, market, explicit, (strength='weak') weak, result, COUNT(*) n FROM wx_article_pick "
                    "GROUP BY wxid, market, explicit, (strength='weak'), result")
        pk: Dict[str, Dict[str, Dict[str, int]]] = {}        # wxid -> market -> result -> n (计入)
        pk_ex: Dict[str, Dict[int, Dict[str, int]]] = {}     # wxid -> explicit -> result -> n (计入)
        weak_n: Dict[str, int] = {}
        for r in cur.fetchall() or []:
            if r["weak"]:
                weak_n[r["wxid"]] = weak_n.get(r["wxid"], 0) + r["n"]
                continue
            d = pk.setdefault(r["wxid"], {}).setdefault(r["market"], {})
            d[r["result"]] = d.get(r["result"], 0) + r["n"]
            e = pk_ex.setdefault(r["wxid"], {}).setdefault(int(r["explicit"]), {})
            e[r["result"]] = e.get(r["result"], 0) + r["n"]
        cur.execute("SELECT a.wxid, c.verify_status, COUNT(*) n FROM wx_article_claim c "
                    "JOIN wx_article a ON a.id=c.article_id GROUP BY a.wxid, c.verify_status")
        cl: Dict[str, Dict[str, int]] = {}
        for r in cur.fetchall() or []:
            cl.setdefault(r["wxid"], {})[r["verify_status"]] = r["n"]
        cur.execute(
            f"SELECT p.wxid, p.market, p.basis, p.line, p.selection, p.explicit, p.strength, p.result, a.id article_id, a.title, {_MATCH_COLS} "
            "FROM wx_article_pick p JOIN wx_article a ON a.id=p.article_id JOIN matches m ON m.match_id=p.match_id "
            "ORDER BY m.match_timestamp DESC, p.id DESC LIMIT 400")
        recent: Dict[str, List[Dict[str, Any]]] = {}
        for r in cur.fetchall() or []:
            lst = recent.setdefault(r["wxid"], [])
            if len(lst) < 10:
                b = _match_brief(r)
                lst.append({"articleId": r["article_id"], "title": r["title"], "market": r["market"], "line": r["line"],
                            "selection": r["selection"], "explicit": bool(r["explicit"]), "strength": r["strength"],
                            "result": r["result"], **b})
    out = []
    for wxid, a in accts.items():
        by_mk = pk.get(wxid, {})
        total: Dict[str, int] = {}
        for mk in by_mk.values():
            for k, v in mk.items():
                total[k] = total.get(k, 0) + v
        rate, ci, decided = _rate(total)
        markets = []
        for mk, rows in by_mk.items():
            r2, _ci, d2 = _rate(rows)
            markets.append({"market": mk, "decided": d2, "rate": r2})
        markets.sort(key=lambda x: -x["decided"])
        split = {}
        for ex, key in ((1, "explicit"), (0, "inferred")):
            rr, cc, dd = _rate(pk_ex.get(wxid, {}).get(ex, {}))
            split[key] = {"decided": dd, "rate": rr, "ci": cc}
        out.append({
            **a, "picks": {"total": sum(total.values()), "pending": total.get("pending", 0), "void": total.get("void", 0),
                           "push": total.get("push", 0), "decided": decided,
                           "hit": total.get("hit", 0), "hhit": total.get("hhit", 0),
                           "hmiss": total.get("hmiss", 0), "miss": total.get("miss", 0)},
            "rate": rate, "ci": ci, "enough": decided >= MIN_SAMPLE, "minSample": MIN_SAMPLE,
            "byMarket": markets, "split": split, "weakExcluded": weak_n.get(wxid, 0), "claims": {k: cl.get(wxid, {}).get(k, 0) for k in ("confirmed", "contradicted", "unverified")},
            "recent": recent.get(wxid, []),
        })
    out.sort(key=lambda x: (-x["picks"]["decided"], -x["articles"]))
    return out


def match_articles_context(match_id: str) -> List[Dict[str, Any]]:
    """供 AI 聊天:本场相关文章(观点/推荐/事实及核实状态)+ 账号历史命中率。"""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT a.id, a.wxid, a.account_name, a.title, a.publish_time, a.summary, x.timing, x.status "
            "FROM wx_article_match x JOIN wx_article a ON a.id=x.article_id WHERE x.match_id=%s "
            "ORDER BY a.publish_time DESC LIMIT 6", (match_id,))
        arts = list(cur.fetchall() or [])
        if not arts:
            return []
        ids = [a["id"] for a in arts]
        ph = ",".join(["%s"] * len(ids))
        cur.execute(f"SELECT article_id, market, line, selection, explicit, strength, reasoning, result FROM wx_article_pick "
                    f"WHERE match_id=%s AND article_id IN ({ph})", (match_id, *ids))
        picks: Dict[int, List[Dict[str, Any]]] = {}
        for r in cur.fetchall() or []:
            picks.setdefault(r["article_id"], []).append(r)
        cur.execute(f"SELECT article_id, claim_type, side, text, verify_status, verify_note FROM wx_article_claim "
                    f"WHERE match_id=%s AND article_id IN ({ph}) ORDER BY id", (match_id, *ids))
        claims: Dict[int, List[Dict[str, Any]]] = {}
        for r in cur.fetchall() or []:
            claims.setdefault(r["article_id"], []).append(r)
    stats = {s["wxid"]: s for s in account_stats()}
    out = []
    for a in arts:
        st = stats.get(a["wxid"]) or {}
        out.append({"account": a["account_name"], "time": _fmt(a["publish_time"]), "title": a["title"],
                    "summary": a["summary"], "timing": a["timing"], "linkStatus": a["status"],
                    "picks": picks.get(a["id"], []), "claims": claims.get(a["id"], []),
                    "decided": (st.get("picks") or {}).get("decided", 0), "rate": st.get("rate"),
                    "enough": st.get("enough", False)})
    return out
