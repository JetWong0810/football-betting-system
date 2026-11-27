"""AI 倾向的事后结算: 把聊天里存下的倾向(含当时的盘口与水位快照)对上比赛结果, 统计命中率、盈亏和盘口走向。
只读库。每场取最后一次带倾向的回复; 以倾向发出时的盘口/水位结算(不是终盘)。"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from database import get_db

from . import edge

_BJ = timezone(timedelta(hours=8))


def _score(cur, match_id: str) -> Optional[Tuple[int, int]]:
    if match_id.startswith("bd_"):
        cur.execute("SELECT score FROM bd_matches WHERE match_id=%s", (match_id,))
        r = cur.fetchone()
        sc = (r or {}).get("score")
        if sc and ":" in str(sc):
            a, b = str(sc).split(":", 1)
            if a.strip().isdigit() and b.strip().isdigit():
                return int(a), int(b)
        return None
    cur.execute("SELECT home_score hs, away_score a FROM matches WHERE match_id=%s", (match_id,))
    r = cur.fetchone()
    if r and r.get("hs") is not None and r.get("a") is not None:
        return int(r["hs"]), int(r["a"])
    return None


def _closing_line(cur, match_id: str) -> Optional[float]:
    """终盘亚盘(原值 正=主让)。优先 500.com Bet365 最后一条, 其次足彩网历史(标准符号取反)。"""
    try:
        cur.execute("SELECT handicap h FROM odds500_ah_ticks WHERE match_id=%s AND company='Bet365' ORDER BY tick_time DESC LIMIT 1", (match_id,))
        r = cur.fetchone()
        if r and r.get("h") is not None:
            return float(r["h"])
    except Exception:  # noqa: BLE001
        pass
    try:
        cur.execute("SELECT close_handicap h FROM jczq_ah_history WHERE match_id=%s AND company IN ('Bet365','bet365','365') LIMIT 1", (match_id,))
        r = cur.fetchone()
        if r and r.get("h") is not None:
            return -float(r["h"])
    except Exception:  # noqa: BLE001
        pass
    return None


def verdict_report(days: int = 30) -> Dict[str, Any]:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, match_id, verdict_json, created_at FROM match_chat_messages WHERE role='assistant' AND verdict_json IS NOT NULL "
            "AND created_at >= NOW() - INTERVAL %s DAY ORDER BY id", (int(days),))
        rows = list(cur.fetchall() or [])
        last: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            try:
                v = json.loads(r["verdict_json"])
            except (TypeError, json.JSONDecodeError):
                continue
            v["_at"] = r["created_at"].strftime("%m-%d %H:%M") if r.get("created_at") else None
            last[r["match_id"]] = v
        dist = {"ah": {}, "ou": {}}
        ah_rows: List[Dict[str, Any]] = []
        ou_rows: List[Dict[str, Any]] = []
        by_strength: Dict[str, List[Dict[str, Any]]] = {}      # 强度 -> 已结算的让球倾向(看"微弱倾向"到底有没有用)
        clv = {"favorable": 0, "unfavorable": 0, "flat": 0}
        pending = no_snap = 0
        detail: List[Dict[str, Any]] = []
        for mid, v in last.items():
            for k in ("ah", "ou"):
                dist[k][v.get(k) or "无"] = dist[k].get(v.get(k) or "无", 0) + 1
            snap = v.get("snap") or {}
            if not snap:
                no_snap += 1
                continue
            sc = _score(cur, mid)
            if sc is None:
                pending += 1
                continue
            item: Dict[str, Any] = {"matchId": mid, "score": f"{sc[0]}-{sc[1]}", "at": v.get("_at")}
            ah, ahs = v.get("ah"), snap.get("ah") or {}
            if ah in ("上盘", "下盘") and ahs:
                res = edge.settle_ah(ah, ahs.get("line"), ahs.get("home"), ahs.get("away"), sc[0], sc[1])
                if res:
                    ah_rows.append(res)
                    by_strength.setdefault(v.get("ah_s") or "未标强度", []).append(res)
                    item["ah"] = {"pick": ah, "line": ahs.get("line"), **res}
                    close = _closing_line(cur, mid)
                    entry = ahs.get("line")
                    if close is not None and entry is not None and float(entry) != 0 and (float(close) > 0) == (float(entry) > 0):
                        d = abs(float(close)) - abs(float(entry))       # >0: 盘口向上盘方向加深
                        fav = d > 1e-9 if ah == "上盘" else d < -1e-9
                        unf = d < -1e-9 if ah == "上盘" else d > 1e-9
                        clv["favorable" if fav else "unfavorable" if unf else "flat"] += 1
            ou, ous = v.get("ou"), snap.get("ou") or {}
            if ou in ("大球", "小球") and ous:
                res = edge.settle_ou(ou, ous.get("line"), ous.get("over"), ous.get("under"), sc[0], sc[1])
                if res:
                    ou_rows.append(res)
                    item["ou"] = {"pick": ou, "line": ous.get("line"), **res}
            detail.append(item)
    return {"days": days, "matches": len(last), "distribution": dist, "settledAh": edge.tally(ah_rows),
            "settledOu": edge.tally(ou_rows), "ahByStrength": {k: edge.tally(rs) for k, rs in by_strength.items()}, "lineMove": clv, "pending": pending, "noSnapshot": no_snap,
            "note": "以倾向发出时的盘口/水位结算(半赢半输按 0.5 计命中,ROI 为每单位本金);lineMove=倾向发出后到终盘,盘口是否朝倾向方向走(favorable)。"
                    "只有部署该功能之后产生、带盘口快照的倾向才会被结算。", "detail": detail[-30:]}
