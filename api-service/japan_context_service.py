"""组装日职辅助情报（只读展示，不参与因子权重）。"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from jczq_similar_odds import is_japan_league
from jp_scraper.db import get_conn
from jp_scraper.zh_display import (
    club_zh,
    lineup_source_zh,
    resolve_player_names_zh,
    source_zh,
    venue_zh,
)

logger = logging.getLogger(__name__)


_WEATHER_ZH = [
    ("のち", "转"), ("時々", "有时"), ("一時", "短时"),
    ("晴", "晴"), ("曇", "阴"), ("雨", "雨"), ("雪", "雪"),
    ("霧", "雾"), ("雷", "雷"), ("大雨", "大雨"), ("強風", "强风"),
]


def _weather_text_zh(text: Optional[str]) -> Optional[str]:
    if not text:
        return text
    out = text
    for a, b in _WEATHER_ZH:
        out = out.replace(a, b)
    return out


def _apply_player_zh(players: List[Dict], name_map: Dict[str, str]) -> List[Dict]:
    out = []
    for p in players or []:
        item = dict(p)
        ja = p.get("name") or ""
        item["nameJa"] = ja
        item["name"] = name_map.get(ja) or ja
        out.append(item)
    return out


def _localize_context(payload: Dict[str, Any]) -> Dict[str, Any]:
    """队名/场馆/球员/来源统一成中文展示字段。"""
    if not payload.get("isJapanLeague"):
        return payload

    # 竞彩中文队名优先；库简称再映射
    home_cn = payload.get("homeTeam") or club_zh(payload.get("homeShort"))
    away_cn = payload.get("awayTeam") or club_zh(payload.get("awayShort"))
    payload["homeShort"] = home_cn or club_zh(payload.get("homeShort"))
    payload["awayShort"] = away_cn or club_zh(payload.get("awayShort"))
    payload["venue"] = venue_zh(payload.get("venue")) or payload.get("venue")
    payload["lineupSource"] = lineup_source_zh(payload.get("lineupSource"))

    wx = payload.get("weather")
    if wx:
        wx = dict(wx)
        wx["weatherText"] = _weather_text_zh(wx.get("weatherText"))
        if wx.get("source"):
            wx["sourceLabel"] = source_zh(wx.get("source"))
        payload["weather"] = wx

    # 收集球员名译
    names = []
    for lu in payload.get("lineups") or []:
        for p in (lu.get("players") or []) + (lu.get("bench") or []):
            if p.get("name"):
                names.append(p["name"])
    for a in payload.get("attackNotes") or []:
        if a.get("name"):
            names.append(a["name"])

    name_map = resolve_player_names_zh(names, apply=True)

    for lu in payload.get("lineups") or []:
        lu["clubShort"] = club_zh(lu.get("clubShort")) or lu.get("clubShort")
        if lu.get("source"):
            lu["sourceLabel"] = source_zh(lu.get("source"))
        lu["players"] = _apply_player_zh(lu.get("players") or [], name_map)
        lu["bench"] = _apply_player_zh(lu.get("bench") or [], name_map)

    for a in payload.get("attackNotes") or []:
        ja = a.get("name") or ""
        a["nameJa"] = ja
        a["name"] = name_map.get(ja) or ja
        a["clubShort"] = club_zh(a.get("clubShort")) or a.get("clubShort")

    return payload


def _norm_name(s: str) -> str:
    s = (s or "").strip()
    s = s.replace("\u3000", "").replace(" ", "").replace("・", "").replace("·", "")
    s = re.sub(r"[（(].*?[）)]", "", s)
    return s.lower()


def _load_json(val):
    if val is None:
        return None
    if isinstance(val, (list, dict)):
        return val
    try:
        return json.loads(val)
    except (TypeError, json.JSONDecodeError):
        return None


def _enrich_players(cur, players: List[Dict], season: str = "2025") -> List[Dict]:
    """给阵容球员挂上赛季进球/出场（模糊名匹配）。"""
    if not players:
        return []
    # 拉一批该季得分榜进内存做归一化匹配（量级百级）
    cur.execute(
        """
        SELECT player_name, goals, apps, club_id
        FROM jp_player_season_stats
        WHERE season=%s AND competition='J1' AND goals IS NOT NULL
        ORDER BY goals DESC
        """,
        (season,),
    )
    stats = cur.fetchall() or []
    index = {}
    for s in stats:
        key = _norm_name(s["player_name"])
        if key and key not in index:
            index[key] = s

    out = []
    for p in players:
        item = {
            "pos": p.get("pos"),
            "num": p.get("num"),
            "name": p.get("name"),
            "goals": None,
            "apps": None,
        }
        key = _norm_name(p.get("name") or "")
        hit = index.get(key)
        if not hit and key:
            # 后缀/前缀模糊
            for k, s in index.items():
                if key in k or k in key:
                    hit = s
                    break
        if hit:
            item["goals"] = hit.get("goals")
            item["apps"] = hit.get("apps")
        out.append(item)
    return out


def get_japan_context(match_id: str) -> Dict[str, Any]:
    """按竞彩 match_id 取日本情报；非日本联赛返回 available=False。"""
    empty = {
        "available": False,
        "isJapanLeague": False,
        "matchId": match_id,
        "jpMatchId": None,
        "lineups": [],
        "weather": None,
        "note": None,
    }
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # 竞彩侧联赛
            cur.execute(
                "SELECT match_id, league_name, home_team_name, away_team_name, match_date "
                "FROM matches WHERE match_id=%s",
                (match_id,),
            )
            m = cur.fetchone()
            if not m:
                empty["note"] = "未找到比赛"
                return empty
            league = m.get("league_name") or ""
            if not is_japan_league(league):
                empty["note"] = "非日本赛事"
                return empty

            cur.execute(
                """
                SELECT m.*, hc.name_ja_short AS home_short, ac.name_ja_short AS away_short,
                       v.name_ja AS venue_name
                FROM jp_matches m
                LEFT JOIN jp_clubs hc ON hc.club_id=m.home_club_id
                LEFT JOIN jp_clubs ac ON ac.club_id=m.away_club_id
                LEFT JOIN jp_venues v ON v.venue_id=m.venue_id
                WHERE m.jczq_match_id=%s
                LIMIT 1
                """,
                (match_id,),
            )
            jp = cur.fetchone()
            if not jp:
                return {
                    "available": True,
                    "isJapanLeague": True,
                    "matchId": match_id,
                    "jpMatchId": None,
                    "league": league,
                    "homeTeam": m.get("home_team_name"),
                    "awayTeam": m.get("away_team_name"),
                    "lineups": [],
                    "weather": None,
                    "venue": None,
                    "kickoffAt": None,
                    "note": "日本库暂无该场映射，可稍后同步",
                }

            jp_id = int(jp["jp_match_id"])
            # 天气：优先 open_meteo（赛前），其次 sfms02
            cur.execute(
                "SELECT * FROM jp_match_weather WHERE jp_match_id=%s ORDER BY FIELD(source,'open_meteo','sfms02'), fetched_at DESC",
                (jp_id,),
            )
            wx_rows = cur.fetchall() or []
            weather = None
            if wx_rows:
                # 合并展示：有预报用预报，有官网补文字
                by_src = {r["source"]: r for r in wx_rows}
                primary = by_src.get("open_meteo") or by_src.get("sfms02") or wx_rows[0]
                official = by_src.get("sfms02")
                weather = {
                    "tempC": primary.get("temp_c"),
                    "precipProb": primary.get("precip_prob"),
                    "windMs": primary.get("wind_ms"),
                    "humidity": (official or primary).get("humidity"),
                    "weatherText": (official or primary).get("weather_text"),
                    "source": primary.get("source"),
                }

            # 阵容：gekisaka 优先（临场），否则 sfms02
            cur.execute(
                """
                SELECT l.*, c.name_ja_short AS club_short
                FROM jp_lineups l
                JOIN jp_clubs c ON c.club_id=l.club_id
                WHERE l.jp_match_id=%s
                ORDER BY FIELD(l.source,'gekisaka','sfms02'), FIELD(l.side,'home','away')
                """,
                (jp_id,),
            )
            lu_rows = cur.fetchall() or []
            # 每侧只留一个来源（gekisaka 优先）
            picked: Dict[str, Dict] = {}
            for r in lu_rows:
                side = r["side"]
                if side in picked:
                    continue
                season = str(jp.get("season") or "2025")
                if "/" in season:
                    # 2026/27 → 用得点榜已有的最近季 2025，若无则尝试前缀年
                    season_key = season.split("/")[0]
                else:
                    season_key = season
                # 得点榜目前主要是 2025；2026 新季先回退 2025
                cur.execute(
                    "SELECT COUNT(*) c FROM jp_player_season_stats WHERE season=%s",
                    (season_key,),
                )
                if (cur.fetchone() or {}).get("c", 0) == 0:
                    season_key = "2025"

                players = _load_json(r.get("players_json")) or []
                bench = _load_json(r.get("bench_json")) or []
                picked[side] = {
                    "side": side,
                    "clubShort": r.get("club_short"),
                    "clubId": r.get("club_id"),
                    "formation": r.get("formation"),
                    "source": r.get("source"),
                    "sourceUrl": r.get("source_url"),
                    "isConfirmed": bool(r.get("is_confirmed")),
                    "players": _enrich_players(cur, players, season=season_key),
                    "bench": _enrich_players(cur, bench, season=season_key),
                    "fetchedAt": str(r.get("fetched_at") or ""),
                }

            lineups = [picked[s] for s in ("home", "away") if s in picked]

            # 进攻点摘要：首发里进球≥5 的球员
            attack_notes = []
            for lu in lineups:
                for p in lu.get("players") or []:
                    g = p.get("goals")
                    if g is not None and g >= 5:
                        attack_notes.append({
                            "side": lu["side"],
                            "clubShort": lu.get("clubShort"),
                            "name": p.get("name"),
                            "goals": g,
                            "apps": p.get("apps"),
                            "pos": p.get("pos"),
                        })
            attack_notes.sort(key=lambda x: -(x.get("goals") or 0))

            source_label = None
            if lineups:
                src = lineups[0].get("source")
                source_label = "ゲキサカ临场" if src == "gekisaka" else "官网公式记录"

            note = None
            if not lineups:
                note = "临场阵容未公布（通常开赛前约1小时发布）"

            payload = {
                "available": True,
                "isJapanLeague": True,
                "matchId": match_id,
                "jpMatchId": jp_id,
                "league": league,
                "competition": jp.get("competition"),
                "homeTeam": m.get("home_team_name"),
                "awayTeam": m.get("away_team_name"),
                "homeShort": jp.get("home_short"),
                "awayShort": jp.get("away_short"),
                "venue": jp.get("venue_name"),
                "kickoffAt": str(jp.get("kickoff_at") or ""),
                "matchDate": str(jp.get("match_date") or ""),
                "status": jp.get("status"),
                "lineups": lineups,
                "lineupSource": source_label,
                "weather": weather,
                "attackNotes": attack_notes[:8],
                "note": note,
            }
            return _localize_context(payload)
    except Exception as e:
        logger.warning("get_japan_context fail %s: %s", match_id, e)
        empty["note"] = f"查询异常: {e}"
        return empty
    finally:
        conn.close()
