"""本赛季比赛库: 比赛基础信息 + 首发/阵型/教练 + 事件(进球/换人/牌的分钟) + 球队统计(射门/xG 等) + 球队与球场。

范围(按用户要求): 只存"联赛当前赛季", 不存跨赛季历史; 不存球员单场数据(体量大、增量价值低)。
抓取: /fixtures?league&season 列出全赛季 -> 只处理已完赛且库里还没有的 -> /fixtures?ids=(每次 20 场)取 events/lineups/statistics。
增量: sync_dates() 用 /fixtures?date= 一次拿当天所有联赛, 筛出我们关心的新完赛场次。
解析函数是纯函数(不联网不连库), 可单测。
"""
from __future__ import annotations

import json
import logging
import math
from typing import Any, Dict, Iterable, List, Optional, Tuple

from database import get_db

from .client import AfClient

logger = logging.getLogger(__name__)

# 竞彩(近一年场次多)与北单涉及的联赛 -> API-Football 联赛 id
LEAGUES: Dict[str, int] = {
    "西甲": 140, "意甲": 135, "欧冠": 2, "英超": 39, "德甲": 78, "欧罗巴": 3, "瑞超": 113, "韩职": 292, "芬超": 244, "挪超": 103,
    "巴甲": 71, "荷甲": 88, "日职J1": 98, "日乙J2": 99, "葡超": 94, "法甲": 61, "英冠": 40, "美职": 253, "亚冠精英": 17, "亚冠二": 18,
    "沙职": 307, "欧协联": 848, "意乙": 136, "英甲": 41, "墨超": 262, "苏超": 179, "荷乙": 89, "西乙": 141, "法乙": 62, "德乙": 79,
}
FINISHED = {"FT", "AET", "PEN"}
BATCH = 20
STAT_KEYS = ("Ball Possession", "Total Shots", "Shots on Goal", "Shots insidebox", "Shots outsidebox", "Blocked Shots", "Corner Kicks",
             "Fouls", "Yellow Cards", "Red Cards", "Offsides", "Total passes", "Passes accurate", "Goalkeeper Saves", "expected_goals")


# ---------------------------------------------------------------- 纯解析
def parse_detail(d: Dict[str, Any]) -> Dict[str, Any]:
    """/fixtures?ids= 的一条 -> {match, venue, lineups[], events[], stats[]}。"""
    fx, lg, tm = d["fixture"], d["league"], d["teams"]
    stats = []
    for s in d.get("statistics") or []:
        kv = {x["type"]: x["value"] for x in s.get("statistics", []) if x.get("type") in STAT_KEYS}
        if kv:
            stats.append({"team_id": s["team"]["id"], "stats": kv})
    lineups = []
    for t in d.get("lineups") or []:
        xi = [{"id": (x.get("player") or {}).get("id"), "name": (x.get("player") or {}).get("name"),
               "pos": (x.get("player") or {}).get("pos"), "grid": (x.get("player") or {}).get("grid")} for x in t.get("startXI") or []]
        subs = [{"id": (x.get("player") or {}).get("id"), "name": (x.get("player") or {}).get("name"),
                 "pos": (x.get("player") or {}).get("pos")} for x in t.get("substitutes") or []]
        lineups.append({"team_id": t["team"]["id"], "formation": t.get("formation"), "coach_id": (t.get("coach") or {}).get("id"),
                        "coach_name": (t.get("coach") or {}).get("name"), "xi": xi, "subs": subs})
    events = []
    for e in d.get("events") or []:
        t = e.get("time") or {}
        events.append({"minute": t.get("elapsed") or 0, "extra": t.get("extra") or 0, "type": e.get("type") or "", "detail": e.get("detail") or "",
                       "team_id": (e.get("team") or {}).get("id") or 0, "player_id": (e.get("player") or {}).get("id") or 0,
                       "player": (e.get("player") or {}).get("name") or "", "assist": (e.get("assist") or {}).get("name")})
    v = fx.get("venue") or {}
    return {
        "match": {"fixture_id": fx["id"], "league_id": lg["id"], "season": lg["season"], "round": lg.get("round"), "ts": fx["timestamp"],
                  "home_id": tm["home"]["id"], "away_id": tm["away"]["id"], "venue_id": v.get("id"), "referee": fx.get("referee"),
                  "status": fx["status"]["short"], "hg": (d.get("goals") or {}).get("home"), "ag": (d.get("goals") or {}).get("away"),
                  "hth": ((d.get("score") or {}).get("halftime") or {}).get("home"), "hta": ((d.get("score") or {}).get("halftime") or {}).get("away"),
                  "has_stats": 1 if stats else 0},
        "venue": {"id": v.get("id"), "name": v.get("name"), "city": v.get("city")} if v.get("id") else None,
        "lineups": lineups, "events": events, "stats": stats,
    }


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# ---------------------------------------------------------------- 写库
def save_detail(p: Dict[str, Any]) -> None:
    m = p["match"]
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO af_match (af_fixture_id, league_id, season, round, match_ts, home_id, away_id, venue_id, referee, status,
                 home_goals, away_goals, ht_home, ht_away, has_stats) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON DUPLICATE KEY UPDATE status=VALUES(status), home_goals=VALUES(home_goals), away_goals=VALUES(away_goals),
                 ht_home=VALUES(ht_home), ht_away=VALUES(ht_away), has_stats=VALUES(has_stats), venue_id=VALUES(venue_id), referee=VALUES(referee)""",
            (m["fixture_id"], m["league_id"], m["season"], m["round"], m["ts"], m["home_id"], m["away_id"], m["venue_id"], m["referee"],
             m["status"], m["hg"], m["ag"], m["hth"], m["hta"], m["has_stats"]))
        v = p.get("venue")
        if v:
            cur.execute("INSERT INTO af_venue (af_venue_id, name, city) VALUES (%s,%s,%s) "
                        "ON DUPLICATE KEY UPDATE name=COALESCE(name, VALUES(name)), city=COALESCE(city, VALUES(city))", (v["id"], v["name"], v["city"]))
        for l in p["lineups"]:
            cur.execute(
                """INSERT INTO af_match_lineup (af_fixture_id, team_id, formation, coach_id, coach_name, xi_json, subs_json) VALUES (%s,%s,%s,%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE formation=VALUES(formation), coach_id=VALUES(coach_id), coach_name=VALUES(coach_name),
                     xi_json=VALUES(xi_json), subs_json=VALUES(subs_json)""",
                (m["fixture_id"], l["team_id"], l["formation"], l["coach_id"], l["coach_name"],
                 json.dumps(l["xi"], ensure_ascii=False), json.dumps(l["subs"], ensure_ascii=False)))
        for e in p["events"]:
            cur.execute(
                """INSERT IGNORE INTO af_match_event (af_fixture_id, minute, extra_minute, type, detail, team_id, player_id, player, assist)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (m["fixture_id"], e["minute"], e["extra"], e["type"], e["detail"], e["team_id"], e["player_id"], e["player"], e["assist"]))
        for s in p["stats"]:
            cur.execute("INSERT INTO af_match_stats (af_fixture_id, team_id, stats_json) VALUES (%s,%s,%s) "
                        "ON DUPLICATE KEY UPDATE stats_json=VALUES(stats_json)", (m["fixture_id"], s["team_id"], json.dumps(s["stats"], ensure_ascii=False)))


def stored_finished_ids(league_id: int, season: int) -> set:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT af_fixture_id FROM af_match WHERE league_id=%s AND season=%s AND status IN ('FT','AET','PEN')", (league_id, season))
        return {int(r["af_fixture_id"]) for r in cur.fetchall()}


# ---------------------------------------------------------------- 抓取
def current_season(c: AfClient, league_id: int) -> Optional[int]:
    lg = c.get("/leagues", {"id": league_id}).get("response", [])
    if not lg:
        return None
    cur = [s for s in lg[0]["seasons"] if s.get("current")]
    return int((cur[0] if cur else lg[0]["seasons"][-1])["year"])


def fetch_details(c: AfClient, ids: List[int]) -> int:
    n = 0
    for i in range(0, len(ids), BATCH):
        chunk = ids[i:i + BATCH]
        for d in c.get("/fixtures", {"ids": "-".join(str(x) for x in chunk)}).get("response", []):
            if d["fixture"]["status"]["short"] in FINISHED:
                save_detail(parse_detail(d))
                n += 1
    return n


def sync_league(c: AfClient, league_id: int, season: Optional[int] = None, apply: bool = True) -> Dict[str, Any]:
    """回填/补齐某联赛当前赛季的已完赛场次。apply=False 只统计不写库。"""
    season = season or current_season(c, league_id)
    if season is None:
        return {"league": league_id, "error": "no_season"}
    fx = c.get("/fixtures", {"league": league_id, "season": season}).get("response", [])
    fin = [int(f["fixture"]["id"]) for f in fx if f["fixture"]["status"]["short"] in FINISHED]
    have = stored_finished_ids(league_id, season) if apply else set()
    todo = [i for i in fin if i not in have]
    n = fetch_details(c, todo) if apply and todo else 0
    return {"league": league_id, "season": season, "finished": len(fin), "todo": len(todo), "saved": n}


def sync_dates(c: AfClient, dates: Iterable[str], league_ids: Optional[Iterable[int]] = None) -> Dict[str, int]:
    """增量: 取指定日期(YYYY-MM-DD)所有联赛的比赛, 把我们关心且已完赛、库里没有的场次抓详情。"""
    wanted = set(league_ids or LEAGUES.values())
    todo: List[int] = []
    for d in dates:
        for f in c.get("/fixtures", {"date": d}).get("response", []):
            if f["league"]["id"] in wanted and f["fixture"]["status"]["short"] in FINISHED:
                todo.append(int(f["fixture"]["id"]))
    if not todo:
        return {"candidates": 0, "saved": 0}
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT af_fixture_id FROM af_match WHERE af_fixture_id IN (%s) AND status IN ('FT','AET','PEN')" % ",".join(["%s"] * len(todo)), tuple(todo))
        have = {int(r["af_fixture_id"]) for r in cur.fetchall()}
    new = [i for i in todo if i not in have]
    return {"candidates": len(todo), "saved": fetch_details(c, new) if new else 0}


def sync_teams(c: AfClient, league_id: int, season: int) -> int:
    """球队 + 主场球场(容量/草皮/城市/地址)。"""
    n = 0
    with get_db() as conn:
        cur = conn.cursor()
        for t in c.get("/teams", {"league": league_id, "season": season}).get("response", []):
            tm, v = t["team"], t.get("venue") or {}
            cur.execute(
                """INSERT INTO af_team (af_team_id, name, code, country, founded, national, venue_id) VALUES (%s,%s,%s,%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE name=VALUES(name), code=VALUES(code), country=VALUES(country), founded=VALUES(founded),
                     national=VALUES(national), venue_id=VALUES(venue_id)""",
                (tm["id"], tm["name"], tm.get("code"), tm.get("country"), tm.get("founded"), 1 if tm.get("national") else 0, v.get("id")))
            if v.get("id"):
                cur.execute(
                    """INSERT INTO af_venue (af_venue_id, name, city, country, address, capacity, surface) VALUES (%s,%s,%s,%s,%s,%s,%s)
                       ON DUPLICATE KEY UPDATE name=VALUES(name), city=VALUES(city), address=VALUES(address), capacity=VALUES(capacity),
                         surface=VALUES(surface), country=COALESCE(country, VALUES(country))""",
                    (v["id"], v.get("name"), v.get("city"), tm.get("country"), v.get("address"), v.get("capacity"), v.get("surface")))
            n += 1
    return n
