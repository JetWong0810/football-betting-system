"""组装一场比赛的 BSD 情报（只读展示，不进因子）。"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from .cache import BsdCache
from .client import BsdClient
from .fetch import fetch_bundle
from .map import get_event_map, load_alias_table, match_one, upsert_event_map
from .assess import build_assessment

logger = logging.getLogger(__name__)
CST = timezone(timedelta(hours=8))

_PACK_TTL = 180
_pack: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_pack_lock = threading.Lock()
_inflight: Dict[str, Tuple[threading.Event, list]] = {}
_inflight_lock = threading.Lock()


def _f_match(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


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
    if not refresh:
        with _pack_lock:
            hit_pack = _pack.get(match_id)
        if hit_pack and time.time() - hit_pack[0] < _PACK_TTL:
            return hit_pack[1]
        joined = _await_inflight(match_id)
        if joined is not None:
            return joined

    owner = _begin_inflight(match_id) if not refresh else False
    t0 = time.time()
    try:
        payload = _build_intel(match_id, match)
    except Exception as e:
        if owner:
            _end_inflight(match_id, err=e)
        raise
    with _pack_lock:
        _pack[match_id] = (time.time(), payload)
    logger.info("intel %s %.1fs available=%s", match_id, time.time() - t0, payload.get("available"))
    if owner:
        _end_inflight(match_id, result=payload)
    return payload


def _await_inflight(match_id: str):
    with _inflight_lock:
        infl = _inflight.get(match_id)
        if infl is None:
            ev, box = threading.Event(), [None, None]
            _inflight[match_id] = (ev, box)
            return None
        ev, box = infl
    ev.wait(timeout=90)
    if box[1] is not None:
        raise box[1]
    return box[0]


def _begin_inflight(match_id: str) -> bool:
    with _inflight_lock:
        return match_id in _inflight


def _end_inflight(match_id: str, result=None, err=None) -> None:
    with _inflight_lock:
        infl = _inflight.pop(match_id, None)
    if not infl:
        return
    ev, box = infl
    box[0], box[1] = result, err
    ev.set()


def _build_intel(match_id: str, match: Dict[str, Any]) -> Dict[str, Any]:
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
            with BsdClient() as client, BsdCache(client) as cache:
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

    with BsdClient() as client, BsdCache(client) as cache:
        bundle = fetch_bundle(cache, int(hit["bsd_event_id"]), extra=hit)
        logger.info("bsd fetch %s reqs=%s", match_id, client.req_n)

    event = bundle.get("event") or {}
    lu = bundle.get("lineups") or {}
    lineups = lu.get("lineups") or {}
    unav = lu.get("unavailable_players") or {}
    home_lu = lineups.get("home") or {}
    away_lu = lineups.get("away") or {}
    venue = bundle.get("venue") or {}
    weather = event.get("weather") or {}
    try:
        assess = build_assessment(
            home_name=match.get("home_team_name") or event.get("home_team") or "主队",
            away_name=match.get("away_team_name") or event.get("away_team") or "客队",
            event=event,
            home_lu=home_lu,
            away_lu=away_lu,
            unav=unav if isinstance(unav, dict) else {},
            recent=bundle.get("recent_lineups") or {},
            standings=bundle.get("standings"),
            fixtures=bundle.get("fixtures") or {},
            profiles=bundle.get("profiles") or {},
            stats=bundle.get("player_stats") or {},
            prediction=bundle.get("prediction"),
            home_team_id=hit.get("home_team_id") or event.get("home_team_id"),
            away_team_id=hit.get("away_team_id") or event.get("away_team_id"),
            handicap_std=(-float(match["asian_handicap"]) if match.get("asian_handicap") is not None else None),
            ah_home_odds=_f_match(match.get("asian_home_odds")),
            ah_away_odds=_f_match(match.get("asian_away_odds")),
            managers=bundle.get("managers") or {},
        )
    except Exception:
        logger.exception("bsd assess failed %s", match_id)
        assess = {"verdicts": [], "facts": [], "sides": {}, "players": {"home": [], "away": []}}

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
        "prediction": bundle.get("prediction"),
        "verdicts": assess.get("verdicts") or [],
        "facts": assess.get("facts") or [],
        "sides": assess.get("sides") or {},
        "players": assess.get("players") or {"home": [], "away": []},
    }
