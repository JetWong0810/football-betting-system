"""按场拉取 BSD 情报包写入 cache。"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from .cache import BsdCache

logger = logging.getLogger(__name__)

CST = timezone(timedelta(hours=8))

TTL_EVENT = 30 * 60
TTL_LINEUP_PRED = 30 * 60
TTL_FIXTURES = 6 * 3600
TTL_HIST_LU = 24 * 3600
TTL_PROFILE = 24 * 3600
TTL_STANDINGS = 12 * 3600
TTL_PLAYER = 24 * 3600
TTL_STATS = 12 * 3600
TTL_PRED = 6 * 3600

_WORKERS = 10


def _finished(ev: Dict[str, Any]) -> bool:
    st = (ev.get("status") or "").lower()
    return st in ("finished", "closed", "complete", "completed")


def _gather(cache: BsdCache, jobs: List[Tuple[str, str, Optional[Dict], int]]) -> Dict[str, Any]:
    """jobs: (key, path, params, ttl_s) → {key: payload}"""
    out: Dict[str, Any] = {}
    if not jobs:
        return out

    def one(job):
        key, path, params, ttl = job
        return key, cache.get_json(path, params=params, ttl_s=ttl)

    if len(jobs) == 1:
        k, v = one(jobs[0])
        return {k: v}
    with ThreadPoolExecutor(max_workers=min(_WORKERS, len(jobs))) as pool:
        futs = [pool.submit(one, j) for j in jobs]
        for f in as_completed(futs):
            k, v = f.result()
            out[k] = v
    return out


def fetch_bundle(cache: BsdCache, event_id: int, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    extra = extra or {}
    wave1 = _gather(cache, [
        ("event", f"/api/v2/events/{event_id}/", None, TTL_EVENT),
        ("lu", f"/api/v2/events/{event_id}/lineups/", None, TTL_LINEUP_PRED),
        ("prediction", f"/api/v2/events/{event_id}/prediction/", None, TTL_PRED),
    ])
    event = wave1.get("event") or {}
    lu = wave1.get("lu") or {}
    prediction = wave1.get("prediction")
    if isinstance(prediction, dict) and prediction.get("detail"):
        prediction = None

    home_id = extra.get("home_team_id") or event.get("home_team_id")
    away_id = extra.get("away_team_id") or event.get("away_team_id")

    jobs2: List[Tuple[str, str, Optional[Dict], int]] = []
    if home_id:
        jobs2.append(("fx_home", f"/api/v2/teams/{int(home_id)}/fixtures/", _fx_params(), TTL_FIXTURES))
    if away_id:
        jobs2.append(("fx_away", f"/api/v2/teams/{int(away_id)}/fixtures/", _fx_params(), TTL_FIXTURES))
    if event.get("home_coach_id"):
        jobs2.append(("mgr_home", f"/api/v2/managers/{event['home_coach_id']}/", None, TTL_PROFILE))
    if event.get("away_coach_id"):
        jobs2.append(("mgr_away", f"/api/v2/managers/{event['away_coach_id']}/", None, TTL_PROFILE))
    if event.get("venue_id"):
        jobs2.append(("venue", f"/api/v2/venues/{event['venue_id']}/", None, TTL_PROFILE))
    if event.get("league_id"):
        jobs2.append(("standings", f"/api/v2/leagues/{event['league_id']}/standings/", None, TTL_STANDINGS))
    wave2 = _gather(cache, jobs2)

    fx_home = wave2.get("fx_home")
    fx_away = wave2.get("fx_away")
    hist_jobs = []
    for key, raw in (("h", fx_home), ("a", fx_away)):
        for eid in _recent_eids(raw, 5):
            hist_jobs.append((f"lu-{eid}", f"/api/v2/events/{eid}/lineups/", None, TTL_HIST_LU))
    hist = _gather(cache, hist_jobs)
    lu_by_id = {}
    for k, v in hist.items():
        if k.startswith("lu-"):
            lu_by_id[int(k[3:])] = v

    recent_lu = {
        "home": _recent_lineups(fx_home, int(home_id) if home_id else None, lu_by_id),
        "away": _recent_lineups(fx_away, int(away_id) if away_id else None, lu_by_id),
    }

    from .assess import relevant_player_ids
    lu_block = lu if isinstance(lu, dict) else {}
    lineups = (lu_block.get("lineups") or {}) if isinstance(lu_block, dict) else {}
    unav = (lu_block.get("unavailable_players") or {}) if isinstance(lu_block, dict) else {}
    pids = relevant_player_ids(
        lineups.get("home") or {},
        lineups.get("away") or {},
        unav if isinstance(unav, dict) else {},
        recent_lu,
    )
    pjobs = []
    for pid in pids:
        pjobs.append((f"p{pid}", f"/api/v2/players/{pid}/", None, TTL_PLAYER))
        pjobs.append((f"s{pid}", f"/api/v2/players/{pid}/stats/", {"limit": 8}, TTL_STATS))
    pwave = _gather(cache, pjobs)
    profiles: Dict[int, Dict[str, Any]] = {}
    stats: Dict[int, List[Dict[str, Any]]] = {}
    for pid in pids:
        prof = pwave.get(f"p{pid}")
        if isinstance(prof, dict) and prof.get("id"):
            profiles[pid] = prof
        st = pwave.get(f"s{pid}")
        rows = (st or {}).get("results") if isinstance(st, dict) else None
        stats[pid] = list(rows or [])

    managers = {}
    if wave2.get("mgr_home"):
        managers["home"] = wave2["mgr_home"]
    if wave2.get("mgr_away"):
        managers["away"] = wave2["mgr_away"]

    return {
        "event": event,
        "lineups": lu,
        "squad": {"home": None, "away": None},
        "fixtures": {"home": _compact_fx(fx_home), "away": _compact_fx(fx_away)},
        "recent_lineups": recent_lu,
        "managers": managers,
        "venue": wave2.get("venue"),
        "standings": wave2.get("standings"),
        "prediction": prediction,
        "profiles": profiles,
        "player_stats": stats,
    }


def _fx_params() -> Dict[str, Any]:
    today = datetime.now(timezone.utc).date()
    return {
        "date_from": (today - timedelta(days=40)).isoformat(),
        "date_to": (today + timedelta(days=14)).isoformat(),
        "limit": 30,
    }


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


def _recent_eids(fx_raw: Any, n: int = 5) -> List[int]:
    rows = (fx_raw or {}).get("results") if isinstance(fx_raw, dict) else (fx_raw or [])
    finished = [r for r in (rows or []) if _finished(r) and r.get("id")]
    finished.sort(key=lambda r: r.get("event_date") or "", reverse=True)
    out = []
    seen = set()
    for r in finished[:n]:
        eid = int(r["id"])
        if eid in seen:
            continue
        seen.add(eid)
        out.append(eid)
    return out


def _recent_lineups(fx_raw: Any, team_id: Optional[int], lu_by_id: Dict[int, Any], n: int = 5) -> List[Dict[str, Any]]:
    rows = (fx_raw or {}).get("results") if isinstance(fx_raw, dict) else (fx_raw or [])
    finished = [r for r in (rows or []) if _finished(r) and r.get("id")]
    finished.sort(key=lambda r: r.get("event_date") or "", reverse=True)
    out = []
    for r in finished[:n]:
        eid = int(r["id"])
        lu = lu_by_id.get(eid)
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
