"""竞彩场次 → API-Football fixture 的对齐。

做法: 按开赛日取 /fixtures?date=(每个日期 1 次请求), 在开赛时间 ±10 分钟内的候选里,
用 已学队名映射(af_team_map, 精确) + BSD 别名表(模糊) 给主客队打分。
  both     两边都 >=0.9 (含映射表命中)
  fuzzy    一边 >=0.9, 另一边 >=0.65
  one_side 一边 >=0.9, 另一边查不到别名, 且候选里只有这一场匹配该边 -> 接受, 并把另一边学进 af_team_map
对不上的不猜, 列出来等人工(set_team 指定)。已在 af_fixture_map 的场次不重复处理。
"""
from __future__ import annotations

import datetime as _dt
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from bsd_intel.map import cn_to_en, load_alias_table, score_pair
from database import get_db

from .client import AfClient

logger = logging.getLogger(__name__)

WINDOW_SEC = 600
ONE_SIDE_MIN = 0.85          # 一边别名分 >= 此值且为唯一候选, 才接受 one_side

# 竞彩联赛名 -> (AF 国家, AF 联赛名关键词)。只用于"同联赛同时间只有唯一一场"时的兜底, 填错只会导致对不上, 不会错配。
LEAGUE_HINT = {
    "英超": ("England", "Premier League"), "英冠": ("England", "Championship"),
    "德甲": ("Germany", "Bundesliga"), "德乙": ("Germany", "2. Bundesliga"),
    "西甲": ("Spain", "La Liga"), "意甲": ("Italy", "Serie A"), "法甲": ("France", "Ligue 1"),
    "荷甲": ("Netherlands", "Eredivisie"), "荷乙": ("Netherlands", "Eerste Divisie"),
    "澳超": ("Australia", "A-League"), "美职": ("USA", "Major League Soccer"),
}


def _table_missing(e: Exception) -> bool:
    return bool(e.args) and e.args[0] == 1146            # 表尚未创建(预览模式): 当作空


def load_team_map() -> Dict[str, Tuple[int, str]]:
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT alias, af_team_id, af_name FROM af_team_map")
            return {r["alias"]: (int(r["af_team_id"]), r["af_name"]) for r in cur.fetchall()}
    except Exception as e:  # noqa: BLE001
        if _table_missing(e):
            return {}
        raise


def side_score(cn: str, team: Dict[str, Any], tmap: Dict[str, Tuple[int, str]], alias: Dict[str, str]) -> float:
    hit = tmap.get(cn)
    if hit:
        return 1.0 if hit[0] == team["id"] else 0.0       # 已学映射是精确的, 不一致就是不同队
    return score_pair(cn, team["name"], alias)


def pick(m: Dict[str, Any], fixtures: List[Dict[str, Any]], tmap, alias) -> Optional[Dict[str, Any]]:
    """返回 {fixture, method, confidence, learn: [(cn, team)]} 或 None。"""
    cands = [f for f in fixtures if abs(f["fixture"]["timestamp"] - m["ts"]) <= WINDOW_SEC]
    scored = []
    for f in cands:
        sh = side_score(m["h"], f["teams"]["home"], tmap, alias)
        sa = side_score(m["a"], f["teams"]["away"], tmap, alias)
        scored.append((sh, sa, f))
    both = [x for x in scored if x[0] >= 0.9 and x[1] >= 0.9]
    if len(both) == 1:
        sh, sa, f = both[0]
        return {"fixture": f, "method": "both", "confidence": round(min(sh, sa), 2), "learn": _learn(m, f, tmap)}
    if len(both) > 1:
        return None
    fuzzy = [x for x in scored if (x[0] >= 0.9 and x[1] >= 0.65) or (x[1] >= 0.9 and x[0] >= 0.65)]
    if len(fuzzy) == 1:
        sh, sa, f = fuzzy[0]
        return {"fixture": f, "method": "fuzzy", "confidence": round(min(sh, sa), 2), "learn": _learn(m, f, tmap)}
    if len(fuzzy) > 1:
        return None
    # one_side: 一边匹配很好, 另一边没有任何别名线索(分数为 0 且不在映射表), 且只有这一场满足
    for side, other_cn_side in (("h", "a"), ("a", "h")):
        idx = 0 if side == "h" else 1
        strong = [x for x in scored if x[idx] >= ONE_SIDE_MIN]
        if len(strong) != 1:
            continue
        sh, sa, f = strong[0]
        other_cn = m[other_cn_side]
        if other_cn in tmap or cn_to_en(other_cn, alias) is not None:
            continue                                         # 另一边在别名/映射表里有记录却对不上: 不能当作没信息
        return {"fixture": f, "method": "one_side", "confidence": 0.7, "learn": _learn(m, f, tmap)}
    # league_unique: 同联赛、同开赛时间窗口内只有唯一一场(已被其他场次占用的不算)
    hint = LEAGUE_HINT.get(m.get("league_name") or "")
    if hint:
        taken = m.get("_taken") or set()
        same = [x for x in scored if x[2]["league"].get("country") == hint[0] and x[2]["league"].get("name") == hint[1]
                and x[2]["fixture"]["id"] not in taken]
        if len(same) == 1:
            sh, sa, _f = same[0]
            for cn, sc in ((m["h"], sh), (m["a"], sa)):
                if sc < 0.65 and (cn in tmap or cn_to_en(cn, alias) is not None):
                    return None                              # 已知队名与候选明显不符: 联赛唯一也不能接受
            return {"fixture": same[0][2], "method": "league_unique", "confidence": 0.6, "learn": _learn(m, same[0][2], tmap)}
    return None


def _learn(m, f, tmap) -> List[Tuple[str, Dict[str, Any]]]:
    out = []
    for cn, team in ((m["h"], f["teams"]["home"]), (m["a"], f["teams"]["away"])):
        if cn and cn not in tmap:
            out.append((cn, team))
    return out


def onsale_matches(back_hours: float = 4) -> List[Dict[str, Any]]:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT match_id, match_code, league_name, home_team_name AS h, away_team_name AS a, match_timestamp AS ts
               FROM matches WHERE match_id NOT LIKE 'jczq%%' AND home_score IS NULL AND match_timestamp > %s
               ORDER BY match_timestamp""", (time.time() - back_hours * 3600,))
        return [dict(r, ts=float(r["ts"])) for r in cur.fetchall()]


def mapped_ids() -> set:
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT match_id FROM af_fixture_map")
            return {r["match_id"] for r in cur.fetchall()}
    except Exception as e:  # noqa: BLE001
        if _table_missing(e):
            return set()
        raise


def save(m, res) -> None:
    f = res["fixture"]
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO af_fixture_map (match_id, af_fixture_id, af_league_id, af_season, af_home_id, af_away_id, method, confidence)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
               ON DUPLICATE KEY UPDATE af_fixture_id=VALUES(af_fixture_id), af_league_id=VALUES(af_league_id),
                 af_season=VALUES(af_season), af_home_id=VALUES(af_home_id), af_away_id=VALUES(af_away_id),
                 method=VALUES(method), confidence=VALUES(confidence)""",
            (m["match_id"], f["fixture"]["id"], f["league"]["id"], f["league"].get("season"),
             f["teams"]["home"]["id"], f["teams"]["away"]["id"], res["method"], res["confidence"]))
        for cn, team in res["learn"]:
            cur.execute(
                "INSERT INTO af_team_map (alias, af_team_id, af_name, source) VALUES (%s,%s,%s,'learned') "
                "ON DUPLICATE KEY UPDATE af_team_id=IF(source='manual', af_team_id, VALUES(af_team_id)), "
                "af_name=IF(source='manual', af_name, VALUES(af_name))",
                (cn, team["id"], team["name"]))


def set_team(alias: str, af_team_id: int, af_name: str) -> None:
    with get_db() as conn:
        conn.cursor().execute(
            "INSERT INTO af_team_map (alias, af_team_id, af_name, source) VALUES (%s,%s,%s,'manual') "
            "ON DUPLICATE KEY UPDATE af_team_id=VALUES(af_team_id), af_name=VALUES(af_name), source='manual'",
            (alias, af_team_id, af_name))


def run(apply: bool = False, client: Optional[AfClient] = None) -> Dict[str, Any]:
    """对在售场次做映射。apply=False 只打印不写库。返回统计与未解决列表。"""
    done = mapped_ids()
    ms = [m for m in onsale_matches() if m["match_id"] not in done]
    out: Dict[str, Any] = {"todo": len(ms), "matched": [], "unresolved": []}
    if not ms:
        return out
    own = client is None
    c = client or AfClient()
    try:
        by_date: Dict[str, List[Dict[str, Any]]] = {}
        for m in ms:
            for off in (0, -1):                     # 开赛时间落在 UTC 日界附近时也取前一天
                d = (_dt.datetime.utcfromtimestamp(m["ts"]) + _dt.timedelta(days=off)).strftime("%Y-%m-%d")
                if off == 0 or _dt.datetime.utcfromtimestamp(m["ts"]).hour == 0:
                    by_date.setdefault(d, [])
        for d in by_date:
            by_date[d] = c.get("/fixtures", {"date": d}).get("response", [])
        fixtures = [f for fs in by_date.values() for f in fs]
        tmap, alias = load_team_map(), load_alias_table()
        taken: set = set()
        pending = []
        for m in ms:
            m["_taken"] = taken
            res = pick(m, fixtures, tmap, alias)
            if res and res["method"] == "league_unique":
                pending.append(m)
                continue
            if res:
                taken.add(res["fixture"]["fixture"]["id"])
            _emit(out, m, res, fixtures, tmap, apply)
        for m in pending:                 # 兜底规则放到最后, 此时已被明确对上的比赛都不在候选里
            res = pick(m, fixtures, tmap, alias)
            if res:
                taken.add(res["fixture"]["fixture"]["id"])
            _emit(out, m, res, fixtures, tmap, apply)
        out["requests"] = c.requests
        out["day_remaining"] = c.day_remaining
        return out
    finally:
        if own:
            c.close()


def _emit(out, m, res, fixtures, tmap, apply) -> None:
    if res:
        if apply:
            save(m, res)
            tmap.update({cn: (t["id"], t["name"]) for cn, t in res["learn"]})   # 同一轮里后面的场次可用
        f = res["fixture"]
        out["matched"].append((m["match_code"], m["h"], m["a"], f["teams"]["home"]["name"], f["teams"]["away"]["name"],
                               f["fixture"]["id"], res["method"]))
    else:
        near = [1 for f in fixtures if abs(f["fixture"]["timestamp"] - m["ts"]) <= WINDOW_SEC]
        out["unresolved"].append((m["match_code"], m["league_name"], m["h"], m["a"], len(near)))
