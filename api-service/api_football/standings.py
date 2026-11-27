"""战意: 用积分榜判断末段(最后 6 轮)每队是争前四、保级线附近还是无欲无求, 给大小球一个已验证的小修正。

验证依据(football-data 20 联赛 8 赛季 53529 场, 2.5 线 Pinnacle 收盘): 赛季最后 6 轮, 至少一方"无欲无求"时大球比市场隐含偏多
+3.6pp(n=3159, 前四个赛季 +4.5pp, 后三个赛季 +2.3pp, 在衰减); 双方都有目标时 -0.6pp(无偏差)。+1pp 约 0.046 球, 所以修正取 +0.10 球。
判定口径与验证一致: 只对"双循环(总轮数=2*(队数-1))、>=16 队、两队都已踢到倒数 6 轮内"的联赛生效, 其余情况不输出, 避免把没验证的情形当证据。
  up    = 距第 4 名积分 <= 2 分/场 * 剩余场次 (仍能争前四, 含已在前四的)
  down  = 积分 - 保级线上第一名 <= 2 分/场 * 剩余场次 (在保级线附近)
  none  = 以上都不是 -> 无欲无求
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from database import get_db

from .client import AfClient

logger = logging.getLogger(__name__)

TTL = 12 * 3600
LAST_ROUNDS = 6
MIN_TEAMS = 16
DELTA_MU = 0.10


def classify(table: List[Dict[str, Any]], n_rounds: int) -> Optional[Dict[str, Dict[str, Any]]]:
    """table: 积分榜(按排名), 每项 {team_id, rank, points, played, description}. 返回 {team_id: {...}} 或 None(不适用)。"""
    n = len(table)
    if n < MIN_TEAMS or n_rounds != 2 * (n - 1):
        return None
    pts = [r["points"] for r in table]
    top4 = pts[3]
    # 保级线上第一名: 第一个带 Relegation 的队的上一名; 没有标签退回倒数第 4 名(与验证样本一致)
    rel_idx = next((i for i, r in enumerate(table) if "relegation" in (r.get("description") or "").lower()), None)
    safe = pts[rel_idx - 1] if rel_idx and rel_idx > 0 else pts[n - 4]
    out: Dict[str, Dict[str, Any]] = {}
    for r in table:
        left = n_rounds - r["played"]
        up = (top4 - r["points"]) <= 2 * left
        down = (r["points"] - safe) <= 2 * left
        out[str(r["team_id"])] = {"rank": r["rank"], "points": r["points"], "played": r["played"], "left": left,
                                  "gap_top4": top4 - r["points"], "gap_safe": r["points"] - safe,
                                  "stake": "up" if up else ("down" if down else "none")}
    return out


def parse_table(resp: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
    try:
        groups = resp[0]["league"]["standings"]
    except (IndexError, KeyError, TypeError):
        return None
    if len(groups) != 1:                    # 分组联赛(如美职联东西部)不适用
        return None
    rows = [{"team_id": x["team"]["id"], "rank": x["rank"], "points": x["points"], "played": x["all"]["played"],
             "description": x.get("description")} for x in groups[0]]
    return sorted(rows, key=lambda r: r["rank"])


def load_cached(league_id: int, season: int) -> Optional[Dict[str, Any]]:
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT payload_json, fetched_at FROM af_standings_cache WHERE af_league_id=%s AND season=%s", (league_id, season))
            r = cur.fetchone()
    except Exception as e:  # noqa: BLE001
        if e.args and e.args[0] == 1146:
            return None
        raise
    if not r or not r.get("payload_json"):
        return None
    return {"data": json.loads(r["payload_json"]), "fetchedAt": r["fetched_at"]}


def fetch(match_id: str, force: bool = False, client: Optional[AfClient] = None) -> Dict[str, Any]:
    from .injuries import _mapping
    mp = _mapping(match_id)
    if not mp or not mp.get("af_league_id") or not mp.get("af_season"):
        return {"ok": False, "reason": "no_mapping"}
    lid, season = int(mp["af_league_id"]), int(mp["af_season"])
    cached = load_cached(lid, season)
    if cached and not force and (datetime.utcnow() - cached["fetchedAt"]).total_seconds() < TTL:
        return {"ok": True, "cached": True}
    own = client is None
    c = client or AfClient()
    try:
        table = parse_table(c.get("/standings", {"league": lid, "season": season}).get("response", []))
        rounds = [x for x in c.get("/fixtures/rounds", {"league": lid, "season": season}).get("response", [])]
        n_rounds = len(rounds) if rounds and all(str(x).startswith("Regular Season") for x in rounds) else 0
        payload = {"table": table, "rounds": n_rounds}
        with get_db() as conn:
            conn.cursor().execute(
                "INSERT INTO af_standings_cache (af_league_id, season, payload_json) VALUES (%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE payload_json=VALUES(payload_json), fetched_at=CURRENT_TIMESTAMP",
                (lid, season, json.dumps(payload, ensure_ascii=False)))
        return {"ok": True, "cached": False}
    except Exception as e:  # noqa: BLE001
        logger.warning("积分榜抓取失败 %s: %s", match_id, e)
        return {"ok": False, "reason": "error"}
    finally:
        if own:
            c.close()


_LABEL = {"up": "仍在争前四(或已在前四)", "down": "在保级线附近", "none": "无欲无求(既够不到前四、也基本脱离保级线)"}


def stakes(match_id: str) -> Optional[Dict[str, Any]]:
    """只读库。末段 6 轮内才返回 {home, away, left, any_none, delta}; 否则 None。"""
    from .injuries import _mapping
    mp = _mapping(match_id)
    if not mp or not mp.get("af_league_id") or not mp.get("af_season"):
        return None
    c = load_cached(int(mp["af_league_id"]), int(mp["af_season"]))
    if not c or not c["data"].get("table") or not c["data"].get("rounds"):
        return None
    table, n_rounds = c["data"]["table"], c["data"]["rounds"]
    cl = classify(table, n_rounds)
    if not cl:
        return None
    h, a = cl.get(str(mp["af_home_id"])), cl.get(str(mp["af_away_id"]))
    if not h or not a or max(h["left"], a["left"]) > LAST_ROUNDS:      # 与验证口径一致: 两队剩余场次(含本场)都 <= 6
        return None
    any_none = h["stake"] == "none" or a["stake"] == "none"
    return {"home": h, "away": a, "n_rounds": n_rounds, "any_none": any_none, "delta": DELTA_MU if any_none else 0.0,
            "fetchedAt": c["fetchedAt"]}


def render(match_id: str, home: str, away: str) -> str:
    s = stakes(match_id)
    if not s:
        return ""
    def one(name, t):
        return (f"{name}: 第 {t['rank']} 名,{t['points']} 分,已赛 {t['played']}/{s['n_rounds']} 轮,距第 4 名 {t['gap_top4']:+d} 分,距保级线 {t['gap_safe']:+d} 分 → {_LABEL[t['stake']]}")
    lines = ["\n【战意】(来源 API-Football 积分榜;赛季最后 6 轮内才会出现)", one(f"主队{home}", s["home"]), one(f"客队{away}", s["away"])]
    if s["any_none"]:
        lines.append("对总进球的影响(回测,5.35 万场,2.5 线): 至少一方无欲无求时大球比市场隐含偏多约 3.6 个百分点(前四个赛季约 4.5,近三个赛季约 2.3,在衰减),"
                     f"折合预期总进球约 +{s['delta']:.2f} 球;已作为单独一行加入【大小球概率分布】,不改变市场 μ。")
    else:
        lines.append("双方都还有目标:回测里这种情形大球概率与市场隐含基本一致(-0.6 个百分点,无偏差),战意不提供额外方向。")
    return "\n".join(lines)
