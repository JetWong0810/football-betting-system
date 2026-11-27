"""球队本赛季风格指标: 阵型序列、相邻两场首发换人数(球队自己的基线)、教练变化、首个换人分钟、本队进球时段。

关键点: 轮换必须用球队自己的基线比较。同样"换 4 人", 对平均只换 1.4 人的球队是极端异常, 对平均换 2.8 人的球队属正常范围。
进球时段在单队层面样本很小(一个赛季十几场、十几个球), 只作描述, 不能当结论。
"""
from __future__ import annotations

import json
from collections import Counter
from typing import Any, Dict, List, Optional

from database import get_db

BUCKETS = (("0-15", 0, 15), ("16-30", 16, 30), ("31-45+", 31, 47), ("46-60", 48, 60), ("61-75", 61, 75), ("76-90+", 76, 130))


def rotation_changes(xis: List[List[int]]) -> List[int]:
    """相邻两场首发里新上场的人数(按球员 id)。"""
    return [len(set(cur) - set(prev)) for prev, cur in zip(xis, xis[1:])]


def bucket_of(minute: int) -> str:
    for name, lo, hi in BUCKETS:
        if lo <= minute <= hi:
            return name
    return "76-90+"


def summarize(matches: List[Dict[str, Any]], first_subs: List[int], goal_minutes: List[int]) -> Dict[str, Any]:
    forms = [m["formation"] for m in matches if m.get("formation")]
    ch = rotation_changes([m["xi"] for m in matches if m.get("xi")])
    coaches = [(m.get("coach_id"), m.get("coach_name")) for m in matches if m.get("coach_id")]
    cur = coaches[-1] if coaches else None
    games_under = 0
    for c in reversed(coaches):
        if cur and c[0] == cur[0]:
            games_under += 1
        else:
            break
    by_side: Dict[str, Counter] = {"home": Counter(), "away": Counter()}
    for m in matches:
        if m.get("formation"):
            by_side["home" if m.get("is_home") else "away"][m["formation"]] += 1
    return {
        "n": len(matches), "formations": forms, "top_formations": Counter(forms).most_common(3),
        "home_top": by_side["home"].most_common(1), "away_top": by_side["away"].most_common(1),
        "changes": ch, "change_mean": round(sum(ch) / len(ch), 2) if ch else None, "change_max": max(ch) if ch else None,
        "coach": cur, "games_under_coach": games_under, "coach_changed": len({c[0] for c in coaches}) > 1,
        "first_sub_mean": round(sum(first_subs) / len(first_subs), 1) if first_subs else None, "first_sub_n": len(first_subs),
        "goal_buckets": dict(Counter(bucket_of(m) for m in goal_minutes)), "goals": len(goal_minutes),
    }


def team_matches(team_id: int, league_id: Optional[int] = None, season: Optional[int] = None, before_ts: Optional[float] = None) -> List[Dict[str, Any]]:
    """球队已完赛场次(旧→新)。league_id/season 为 None 时取该队所有已入库赛事(联赛+杯赛+欧战), 轮换常发生在赛事之间。"""
    sql = ("SELECT m.af_fixture_id AS fid, m.match_ts AS ts, m.league_id AS lid, (m.home_id=%s) AS is_home, l.formation, l.coach_id, l.coach_name, l.xi_json, "
           "m.home_goals, m.away_goals FROM af_match m JOIN af_match_lineup l ON l.af_fixture_id=m.af_fixture_id AND l.team_id=%s "
           "WHERE (m.home_id=%s OR m.away_id=%s) AND m.status IN ('FT','AET','PEN')")
    args: List[Any] = [team_id, team_id, team_id, team_id]
    if league_id is not None:
        sql += " AND m.league_id=%s"
        args.append(league_id)
    if season is not None:
        sql += " AND m.season=%s"
        args.append(season)
    if before_ts is not None:
        sql += " AND m.match_ts < %s"
        args.append(before_ts)
    sql += " ORDER BY m.match_ts"
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(sql, tuple(args))
        rows = cur.fetchall()
    out = []
    for r in rows:
        players = [p for p in json.loads(r["xi_json"] or "[]") if p.get("id")]
        out.append({"fid": r["fid"], "ts": float(r["ts"]), "lid": r["lid"], "is_home": bool(r["is_home"]), "formation": r["formation"], "coach_id": r["coach_id"],
                    "coach_name": r["coach_name"], "xi": [p["id"] for p in players], "names": {p["id"]: p.get("name") for p in players},
                    "gf": r["home_goals"] if r["is_home"] else r["away_goals"], "ga": r["away_goals"] if r["is_home"] else r["home_goals"]})
    return out


def team_style(team_id: int, league_id: Optional[int] = None, season: Optional[int] = None, before_ts: Optional[float] = None) -> Dict[str, Any]:
    ms = team_matches(team_id, league_id, season, before_ts)
    if not ms:
        return summarize([], [], [])
    ids = [m["fid"] for m in ms]
    ph = ",".join(["%s"] * len(ids))
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT af_fixture_id AS fid, MIN(minute) AS m FROM af_match_event WHERE team_id=%s AND type='subst' AND af_fixture_id IN ({ph}) GROUP BY af_fixture_id",
                    (team_id, *ids))
        subs = [int(r["m"]) for r in cur.fetchall()]
        cur.execute(f"SELECT minute FROM af_match_event WHERE team_id=%s AND type='Goal' AND detail<>'Missed Penalty' AND af_fixture_id IN ({ph})", (team_id, *ids))
        goals = [int(r["minute"]) for r in cur.fetchall()]
    return summarize(ms, subs, goals)


def compare_lineup(xi_ids: List[int], formation: Optional[str], ms: List[Dict[str, Any]], is_home: bool) -> Dict[str, Any]:
    """本场首发 vs 球队自己的历史: 阵型是否变化、换人数相对基线(均值/最大值)是否异常。ms 为本场之前的比赛(旧→新)。"""
    st = summarize(ms, [], [])
    last = ms[-1] if ms else None
    out: Dict[str, Any] = {"games": len(ms)}
    if last:
        out["vs_last_changes"] = len(set(xi_ids) - set(last["xi"]))
        out["last_formation"] = last["formation"]
        out["formation_changed"] = bool(formation and last["formation"] and formation != last["formation"])
    side = [m["formation"] for m in ms if m.get("formation") and m["is_home"] == is_home]
    out["side_usual"] = Counter(side).most_common(1)[0][0] if side else None
    if st["change_mean"] is not None and out.get("vs_last_changes") is not None:
        out["abnormal"] = out["vs_last_changes"] > (st["change_max"] or 0) and out["vs_last_changes"] >= st["change_mean"] + 2
        out["baseline_mean"], out["baseline_max"] = st["change_mean"], st["change_max"]
    return out
