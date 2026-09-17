"""按场拉取 BSD 情报包写入 cache。"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .cache import BsdCache

logger = logging.getLogger(__name__)

CST = timezone(timedelta(hours=8))

TTL_EVENT = 30 * 60
TTL_LINEUP_PRED = 30 * 60
TTL_LINEUP_CONF = 24 * 3600
TTL_SQUAD = 2 * 3600
TTL_FIXTURES = 6 * 3600
TTL_HIST_LU = 24 * 3600
TTL_PROFILE = 24 * 3600
TTL_STANDINGS = 12 * 3600


def _finished(ev: Dict[str, Any]) -> bool:
    st = (ev.get("status") or "").lower()
    return st in ("finished", "closed", "complete", "completed")


def fetch_bundle(cache: BsdCache, event_id: int, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    extra = extra or {}
    event = cache.get_json(f"/api/v2/events/{event_id}/", ttl_s=TTL_EVENT) or {}
    lu = cache.get_json(f"/api/v2/events/{event_id}/lineups/", ttl_s=TTL_LINEUP_PRED) or {}
    status = (lu.get("lineup_status") or "") if isinstance(lu, dict) else ""
    if status == "confirmed":
        # 已确认则用长 TTL 再读一次命中刚写入的行
        pass

    home_id = extra.get("home_team_id") or event.get("home_team_id")
    away_id = extra.get("away_team_id") or event.get("away_team_id")
    squad_home = squad_away = None
    fx_home = fx_away = None
    if home_id:
        squad_home = cache.get_json(f"/api/v2/teams/{home_id}/squad/", ttl_s=TTL_SQUAD)
        fx_home = _team_fixtures(cache, int(home_id))
    if away_id:
        squad_away = cache.get_json(f"/api/v2/teams/{away_id}/squad/", ttl_s=TTL_SQUAD)
        fx_away = _team_fixtures(cache, int(away_id))

    recent_lu = {
        "home": _recent_lineups(cache, fx_home, int(home_id) if home_id else None),
        "away": _recent_lineups(cache, fx_away, int(away_id) if away_id else None),
    }

    managers = {}
    for side, cid in (("home", event.get("home_coach_id")), ("away", event.get("away_coach_id"))):
        if cid:
            managers[side] = cache.get_json(f"/api/v2/managers/{cid}/", ttl_s=TTL_PROFILE)

    venue = None
    if event.get("venue_id"):
        venue = cache.get_json(f"/api/v2/venues/{event['venue_id']}/", ttl_s=TTL_PROFILE)

    standings = None
    lid = event.get("league_id")
    if lid:
        standings = cache.get_json(f"/api/v2/leagues/{lid}/standings/", ttl_s=TTL_STANDINGS)

    return {
        "event": event,
        "lineups": lu,
        "squad": {"home": squad_home, "away": squad_away},
        "fixtures": {"home": _compact_fx(fx_home), "away": _compact_fx(fx_away)},
        "recent_lineups": recent_lu,
        "managers": managers,
        "venue": venue,
        "standings": standings,
    }


def _team_fixtures(cache: BsdCache, team_id: int) -> Any:
    today = datetime.now(timezone.utc).date()
    return cache.get_json(
        f"/api/v2/teams/{team_id}/fixtures/",
        params={
            "date_from": (today - timedelta(days=40)).isoformat(),
            "date_to": (today + timedelta(days=14)).isoformat(),
            "limit": 30,
        },
        ttl_s=TTL_FIXTURES,
    )


def _compact_fx(raw: Any) -> List[Dict[str, Any]]:
    rows = (raw or {}).get("results") if isinstance(raw, dict) else (raw or [])
    out = []
    for r in rows or []:
        out.append({
            "id": r.get("id"),
            "event_date": r.get("event_date"),
            "status": r.get("status"),
            "home_team": r.get("home_team"),
            "away_team": r.get("away_team"),
            "home_team_id": r.get("home_team_id"),
            "away_team_id": r.get("away_team_id"),
            "home_score": r.get("home_score"),
            "away_score": r.get("away_score"),
            "league_id": r.get("league_id"),
        })
    return out


def _recent_lineups(cache: BsdCache, fx_raw: Any, team_id: Optional[int], n: int = 5) -> List[Dict[str, Any]]:
    rows = (fx_raw or {}).get("results") if isinstance(fx_raw, dict) else (fx_raw or [])
    finished = [r for r in (rows or []) if _finished(r) and r.get("id")]
    finished.sort(key=lambda r: r.get("event_date") or "", reverse=True)
    out = []
    for r in finished[:n]:
        eid = int(r["id"])
        lu = cache.get_json(f"/api/v2/events/{eid}/lineups/", ttl_s=TTL_HIST_LU)
        side = None
        if team_id and r.get("home_team_id") == team_id:
            side = "home"
        elif team_id and r.get("away_team_id") == team_id:
            side = "away"
        out.append({
            "event_id": eid,
            "event_date": r.get("event_date"),
            "home_team": r.get("home_team"),
            "away_team": r.get("away_team"),
            "home_score": r.get("home_score"),
            "away_score": r.get("away_score"),
            "side": side,
            "lineup_status": (lu or {}).get("lineup_status") if isinstance(lu, dict) else None,
            "lineups": (lu or {}).get("lineups") if isinstance(lu, dict) else None,
        })
    return out
