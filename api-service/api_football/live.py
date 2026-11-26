"""滚球记录: 对"已映射且在比赛窗口内"的竞彩场次, 每分钟记录一次滚球赔率 + 比分/事件/统计。

请求量: 每个 tick 固定 2 次 —— /odds/live(全部在赛场次一次拿完) + /fixtures?ids=(最多 20 场一次拿完), 与同时在赛场数无关。
只在赔率更新时间或比分/分钟变化时才新增一行(唯一键去重), 平静期不会堆数据。
事件表记录 first_seen_at, 之后可以拿它和实际进球时间对比, 量出接口延迟。
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from database import get_db

from .client import AfClient

logger = logging.getLogger(__name__)

INTERVAL = int(os.getenv("AF_LIVE_INTERVAL_SEC", "60"))
PRE_SEC = 5 * 60                 # 开赛前 5 分钟开始记录
POST_SEC = 3 * 3600 + 15 * 60    # 开赛后 3 小时 15 分钟(含加时/点球)
DONE = {"FT", "AET", "PEN", "CANC", "ABD", "AWD", "WO", "PST"}
MARKETS = ("Asian Handicap", "Over/Under Line", "Fulltime Result", "Total Corners")
_STAT_KEYS = ("Ball Possession", "Total Shots", "Shots on Goal", "Corner Kicks", "Fouls", "Yellow Cards", "Red Cards",
              "Offsides", "expected_goals")


def _f(x) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def main_pair(values: List[Dict[str, Any]], home_word="Home", away_word="Away",
              away_negated: bool = False) -> Optional[Tuple[float, float, float]]:
    """从同一市场的多条线里选主线, 返回 (线, 主队赔率, 客队赔率)。
    away_negated: 亚盘里客队一侧的盘口是主队的相反数(主 +4.5 对客 -4.5), 配对时要取反; 大小球两边同一条线。
    优先接口标了 main=True 的那一条; 没标就取两边赔率最接近的一条(水位最平衡)。"""
    by_line: Dict[float, Dict[str, float]] = {}
    mains = set()
    for v in values or []:
        ln, od = _f(v.get("handicap")), _f(v.get("odd"))
        if ln is None or od is None or v.get("suspended"):
            continue
        side = "h" if v.get("value") in (home_word, "Over") else "a" if v.get("value") in (away_word, "Under") else None
        if side:
            if side == "a" and away_negated:
                ln = -ln
            by_line.setdefault(ln, {})[side] = od
            if v.get("main"):
                mains.add(ln)
    full = {ln: d for ln, d in by_line.items() if "h" in d and "a" in d}
    if not full:
        return None
    pool = [ln for ln in full if ln in mains] or list(full)
    ln = min(pool, key=lambda x: abs(full[x]["h"] - full[x]["a"]))
    return ln, full[ln]["h"], full[ln]["a"]


def parse_odds(entry: Dict[str, Any]) -> Dict[str, Any]:
    """/odds/live 的一条 -> {update, ah:(line,h,a), ou:(line,o,u), raw:{market: values}}"""
    raw = {m["name"]: m.get("values") for m in entry.get("odds", []) if m.get("name") in MARKETS}
    ah = main_pair(raw.get("Asian Handicap"), away_negated=True)
    ou = main_pair(raw.get("Over/Under Line"), "Over", "Under")
    return {"update": entry.get("update") or "", "ah": ah, "ou": ou, "raw": raw,
            "stopped": bool((entry.get("status") or {}).get("stopped"))}


def parse_stats(fx: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for s in fx.get("statistics") or []:
        side = "home" if (s.get("team") or {}).get("id") == fx["teams"]["home"]["id"] else "away"
        out[side] = {x["type"]: x["value"] for x in s.get("statistics", []) if x.get("type") in _STAT_KEYS}
    return out


def window_matches(now: Optional[float] = None) -> List[Dict[str, Any]]:
    now = now or time.time()
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT f.match_id, f.af_fixture_id, f.af_home_id
               FROM af_fixture_map f JOIN matches m ON m.match_id=f.match_id
               WHERE m.match_timestamp BETWEEN %s AND %s
                 AND NOT EXISTS (SELECT 1 FROM af_live_snapshots s
                                 WHERE s.af_fixture_id=f.af_fixture_id AND s.status IN ('FT','AET','PEN'))""",
            (now - POST_SEC, now + PRE_SEC))
        return list(cur.fetchall())


def tick(client: Optional[AfClient] = None, now: Optional[float] = None) -> Dict[str, int]:
    """记录一次。返回 {'fixtures': n, 'rows': 新增快照数, 'events': 新增事件数}。"""
    ms = window_matches(now)
    res = {"fixtures": 0, "rows": 0, "events": 0}
    if not ms:
        return res
    own = client is None
    c = client or AfClient()
    try:
        by_fid = {int(m["af_fixture_id"]): m for m in ms}
        ids = "-".join(str(i) for i in list(by_fid)[:20])
        fxs = {int(f["fixture"]["id"]): f for f in c.get("/fixtures", {"ids": ids}).get("response", [])}
        live = {fid: f for fid, f in fxs.items() if f["fixture"]["status"]["short"] not in DONE | {"NS", "TBD"}}
        # 刚结束的场次再记一次终态(比分/事件), 之后不会再进入窗口循环里的赔率请求
        odds = {}
        if live:
            for e in c.get("/odds/live").get("response", []):
                fid = int(e["fixture"]["id"])
                if fid in by_fid:
                    odds[fid] = parse_odds(e)
        with get_db() as conn:
            cur = conn.cursor()
            for fid, f in fxs.items():
                st = f["fixture"]["status"]
                short = st.get("short")
                if short in ("NS", "TBD"):
                    continue
                m = by_fid[fid]
                res["fixtures"] += 1
                o = odds.get(fid)
                g = f.get("goals") or {}
                ah, ou = (o or {}).get("ah"), (o or {}).get("ou")
                cur.execute(
                    """INSERT IGNORE INTO af_live_snapshots
                       (match_id, af_fixture_id, odds_updated_at, status, elapsed, goals_home, goals_away,
                        ah_line, ah_home, ah_away, ou_line, ou_over, ou_under, odds_json, stats_json)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (m["match_id"], fid, (o or {}).get("update", ""), short, st.get("elapsed"), g.get("home"), g.get("away"),
                     ah[0] if ah else None, ah[1] if ah else None, ah[2] if ah else None,
                     ou[0] if ou else None, ou[1] if ou else None, ou[2] if ou else None,
                     json.dumps(o["raw"], ensure_ascii=False) if o else None,
                     json.dumps(parse_stats(f), ensure_ascii=False)))
                res["rows"] += cur.rowcount
                for e in f.get("events") or []:
                    tm, pl, asst = e.get("team") or {}, e.get("player") or {}, e.get("assist") or {}
                    t = e.get("time") or {}
                    cur.execute(
                        """INSERT IGNORE INTO af_live_events
                           (match_id, af_fixture_id, minute, extra_minute, type, detail, team_id, player, assist)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (m["match_id"], fid, t.get("elapsed") or 0, t.get("extra") or 0, e.get("type") or "", e.get("detail") or "",
                         tm.get("id") or 0, pl.get("name") or "", asst.get("name")))
                    res["events"] += cur.rowcount
        return res
    finally:
        if own:
            c.close()


def _loop() -> None:
    time.sleep(90)
    while True:
        try:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute("SELECT GET_LOCK('af_live_loop', 0) AS ok")
                if (cur.fetchone() or {}).get("ok"):
                    try:
                        r = tick()
                        if r["rows"] or r["events"]:
                            logger.info("滚球记录: %s 场, 新增快照 %s, 新增事件 %s", r["fixtures"], r["rows"], r["events"])
                    finally:
                        cur.execute("SELECT RELEASE_LOCK('af_live_loop')")
        except Exception:  # noqa: BLE001
            logger.exception("滚球记录异常")
        time.sleep(INTERVAL)


def start() -> None:
    if not (os.getenv("API_FOOTBALL_KEY") or "").strip():
        return
    from . import schema
    try:
        schema.ensure_tables()
    except Exception:  # noqa: BLE001
        logger.exception("滚球记录建表失败")
        return
    threading.Thread(target=_loop, daemon=True, name="af-live").start()
