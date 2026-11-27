"""球员赛季统计(出场/首发/分钟/进球) -> 判断伤停球员、首发缺席球员是不是主力。

口径: 只统计"本场所属联赛"的赛季数据(af_fixture_map 里的 league/season), 不把杯赛混进去。
球队已赛场次取该队球员中最大的出场次数(必有人踢满), 样本小(<5 场)时标注。
分类: 主力 = 分钟占比>=50% 或首发率>=60%; 轮换 = 分钟占比>=20%; 其余为边缘。
局限: 新援/伤愈复出的球员分钟偏低, 不代表不重要; 接口里的位置是"本赛季最常见位置", 与 squads 里的位置可能不一致。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from database import get_db

from .client import AfClient

logger = logging.getLogger(__name__)

TTL = 24 * 3600
MIN_GAMES = 5
POS_ZH = {"Goalkeeper": "门将", "Defender": "后卫", "Midfielder": "中场", "Attacker": "前锋"}


def classify(minutes: Optional[int], starts: Optional[int], games: int) -> str:
    """games: 球队本联赛已赛场次。返回 主力/轮换/边缘。"""
    if not games:
        return "未知"
    share = (minutes or 0) / (games * 90.0)
    srate = (starts or 0) / games
    if share >= 0.5 or srate >= 0.6:
        return "主力"
    if share >= 0.2:
        return "轮换"
    return "边缘"


def parse_players(pages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """多页 /players 返回 -> {'games': 球队已赛, 'players': {id: {...}}}"""
    rows: Dict[str, Dict[str, Any]] = {}
    for d in pages:
        for x in d.get("response", []):
            p = x.get("player") or {}
            sts = x.get("statistics") or []
            if not p.get("id") or not sts:
                continue
            g = (sts[0].get("games") or {})
            rows[str(p["id"])] = {"name": p.get("name"), "pos": g.get("position"), "apps": g.get("appearences") or 0,
                                  "starts": g.get("lineups") or 0, "minutes": g.get("minutes") or 0,
                                  "goals": (sts[0].get("goals") or {}).get("total") or 0}
    games = max([r["apps"] for r in rows.values()] or [0])
    for r in rows.values():
        r["role"] = classify(r["minutes"], r["starts"], games)
        r["share"] = round(r["minutes"] / (games * 90.0), 2) if games else None
    return {"games": games, "players": rows}


def team_stats(c: AfClient, team_id: int, league_id: int, season: int) -> Dict[str, Any]:
    """带 24 小时缓存; 失败返回空结构(调用方降级为不标注)。"""
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT payload_json, fetched_at FROM af_player_stats_cache WHERE af_team_id=%s AND af_league_id=%s AND season=%s",
                        (team_id, league_id, season))
            r = cur.fetchone()
        if r and r.get("payload_json") and (datetime.utcnow() - r["fetched_at"]).total_seconds() < TTL:
            return json.loads(r["payload_json"])
    except Exception as e:  # noqa: BLE001
        logger.warning("球员统计缓存读取失败: %s", e)
    try:
        pages, page = [], 1
        while page <= 4:
            d = c.get("/players", {"team": team_id, "league": league_id, "season": season, "page": page})
            pages.append(d)
            if page >= int((d.get("paging") or {}).get("total") or 1):
                break
            page += 1
        out = parse_players(pages)
        with get_db() as conn:
            conn.cursor().execute(
                "INSERT INTO af_player_stats_cache (af_team_id, af_league_id, season, payload_json) VALUES (%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE payload_json=VALUES(payload_json), fetched_at=CURRENT_TIMESTAMP",
                (team_id, league_id, season, json.dumps(out, ensure_ascii=False)))
        return out
    except Exception as e:  # noqa: BLE001
        logger.warning("球员统计抓取失败 team=%s league=%s: %s", team_id, league_id, e)
        return {"games": 0, "players": {}}


def tag(p: Dict[str, Any], games: int) -> str:
    """一个球员的简短标注: 首发 6/11、分钟占比 53%、进球 5"""
    s = f"首发 {p['starts']}/{games}、分钟占比 {int((p.get('share') or 0) * 100)}%"
    if p.get("goals"):
        s += f"、进球 {p['goals']}"
    return s
