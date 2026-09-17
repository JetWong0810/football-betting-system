"""组装一场比赛的 BSD 情报（只读展示，不进因子）。"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from . import db
from .cache import BsdCache
from .client import BsdClient
from .fetch import fetch_bundle
from .map import get_event_map, load_alias_table, match_one, upsert_event_map

logger = logging.getLogger(__name__)
CST = timezone(timedelta(hours=8))


def _xi(side_block: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not side_block:
        return []
    out = []
    for p in side_block.get("players") or []:
        out.append({
            "id": p.get("id"),
            "name": p.get("short_name") or p.get("name"),
            "fullName": p.get("name"),
            "pos": p.get("position"),
            "num": p.get("jersey_number"),
            "aiScore": p.get("ai_score"),
            "captain": bool(p.get("captain")),
        })
    return out


def _unavail(block: Any) -> List[Dict[str, Any]]:
    if not block:
        return []
    out = []
    for p in block:
        out.append({
            "id": p.get("id"),
            "name": p.get("short_name") or p.get("name"),
            "status": p.get("status") or p.get("availability"),
            "reason": p.get("reason") or p.get("injury_type"),
        })
    return out


def get_intel(match_id: str, match: Dict[str, Any], refresh: bool = False) -> Dict[str, Any]:
    mapped = get_event_map(match_id)
    hit = None
    if mapped:
        hit = {
            "bsd_event_id": mapped["bsd_event_id"],
            "home_team_id": mapped.get("home_team_id"),
            "away_team_id": mapped.get("away_team_id"),
            "confidence": mapped.get("confidence"),
        }
    else:
        ts = int(match.get("match_timestamp") or 0)
        if ts:
            day = datetime.fromtimestamp(ts, timezone.utc).date()
            table = load_alias_table()
            with BsdClient() as client:
                cache = BsdCache(client)
                page = cache.get_json(
                    "/api/v2/events/",
                    params={
                        "date_from": (day - timedelta(days=1)).isoformat(),
                        "date_to": (day + timedelta(days=1)).isoformat(),
                        "limit": 200,
                    },
                    ttl_s=20 * 60,
                ) or {}
                events = page.get("results") or []
                found = match_one(
                    match.get("home_team_name") or "",
                    match.get("away_team_name") or "",
                    ts,
                    events,
                    table,
                )
                if found:
                    found["jczq_home"] = match.get("home_team_name")
                    found["jczq_away"] = match.get("away_team_name")
                    upsert_event_map(match_id, found)
                    hit = found
        if not hit:
            return {
                "available": False,
                "reason": "unmatched",
                "matchId": match_id,
                "homeTeam": match.get("home_team_name"),
                "awayTeam": match.get("away_team_name"),
            }

    with BsdClient() as client:
        cache = BsdCache(client)
        bundle = fetch_bundle(cache, int(hit["bsd_event_id"]), extra=hit)

    event = bundle.get("event") or {}
    lu = bundle.get("lineups") or {}
    lineups = lu.get("lineups") or {}
    unav = lu.get("unavailable_players") or {}
    home_lu = lineups.get("home") or {}
    away_lu = lineups.get("away") or {}
    venue = bundle.get("venue") or {}
    weather = event.get("weather") or {}

    return {
        "available": True,
        "matchId": match_id,
        "bsdEventId": hit["bsd_event_id"],
        "confidence": hit.get("confidence"),
        "homeTeam": match.get("home_team_name"),
        "awayTeam": match.get("away_team_name"),
        "homeTeamId": hit.get("home_team_id") or event.get("home_team_id"),
        "awayTeamId": hit.get("away_team_id") or event.get("away_team_id"),
        "bsdHome": event.get("home_team"),
        "bsdAway": event.get("away_team"),
        "kickoff": event.get("event_date"),
        "lineupStatus": lu.get("lineup_status"),
        "lineupUpdatedAt": lu.get("updated_at"),
        "venue": {
            "name": venue.get("name"),
            "city": venue.get("city"),
            "capacity": venue.get("capacity"),
        } if venue else None,
        "weather": weather,
        "travelKm": event.get("travel_distance_km"),
        "isDerby": event.get("is_local_derby"),
        "isNeutral": event.get("is_neutral_ground"),
        "managers": bundle.get("managers") or {},
        "unavailable": {
            "home": _unavail(unav.get("home") if isinstance(unav, dict) else None),
            "away": _unavail(unav.get("away") if isinstance(unav, dict) else None),
        },
        "predicted": {
            "home": {
                "formation": home_lu.get("formation"),
                "confidence": home_lu.get("confidence"),
                "players": _xi(home_lu),
            },
            "away": {
                "formation": away_lu.get("formation"),
                "confidence": away_lu.get("confidence"),
                "players": _xi(away_lu),
            },
        },
        "recentLineups": bundle.get("recent_lineups") or {},
        "h2h": event.get("head_to_head"),
        "standings": bundle.get("standings"),
        "fetchedHint": "raw cache; 对照/重要性逻辑后补",
    }
