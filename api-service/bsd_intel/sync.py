#!/usr/bin/env python3
"""BSD 情报同步。

  cd api-service
  python3 -m bsd_intel.sync --dry-run
  python3 -m bsd_intel.sync --apply
  python3 -m bsd_intel.sync --apply --days 3
  python3 -m bsd_intel.sync --apply --kickoff-soon
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from . import db
from .aliases import TEAM_SEEDS
from .cache import BsdCache
from .client import BsdClient
from .fetch import fetch_bundle
from .map import get_event_map, load_alias_table, match_one, seed_team_map, upsert_event_map

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("bsd_sync")

CST = timezone(timedelta(hours=8))


def list_jczq(days: int) -> List[Dict[str, Any]]:
    now = int(time.time())
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT match_id, match_number, league_name, match_timestamp,
                       home_team_name, away_team_name
                FROM matches
                WHERE project_type='football'
                  AND match_timestamp >= %s
                  AND match_timestamp < %s
                ORDER BY match_timestamp
                """,
                (now - 3600, now + days * 86400),
            )
            return list(cur.fetchall() or [])
    finally:
        conn.close()


def list_bsd_events(cache: BsdCache, date_from: str, date_to: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    offset = 0
    while True:
        page = cache.get_json(
            "/api/v2/events/",
            params={"date_from": date_from, "date_to": date_to, "limit": 200, "offset": offset},
            ttl_s=20 * 60,
        ) or {}
        rows = page.get("results") or []
        out.extend(rows)
        if not page.get("next") or not rows:
            break
        offset += 200
        if offset > 2000:
            break
    return out


def sync(days: int, apply: bool, limit: Optional[int], kickoff_soon: bool) -> None:
    db.ensure_schema(apply=apply)
    if apply:
        n = seed_team_map()
        logger.info("team map seeds upserted=%s", n)

    rows = list_jczq(days)
    if kickoff_soon:
        now = int(time.time())
        rows = [r for r in rows if now <= int(r["match_timestamp"] or 0) <= now + 2 * 3600]
    if limit:
        rows = rows[:limit]
    logger.info("jczq candidates=%s apply=%s", len(rows), apply)

    if not rows:
        return

    ts_list = [int(r["match_timestamp"] or 0) for r in rows]
    d0 = datetime.fromtimestamp(min(ts_list), timezone.utc).date()
    d1 = datetime.fromtimestamp(max(ts_list), timezone.utc).date()
    date_from = (d0 - timedelta(days=1)).isoformat()
    date_to = (d1 + timedelta(days=1)).isoformat()

    table = load_alias_table() if apply else {a: n for a, n in TEAM_SEEDS}

    with BsdClient() as client, BsdCache(client) as cache:
        if apply:
            events = list_bsd_events(cache, date_from, date_to)
        else:
            events = []
            offset = 0
            while True:
                r = client.get(
                    "/api/v2/events/",
                    params={"date_from": date_from, "date_to": date_to, "limit": 200, "offset": offset},
                )
                page = r.json()
                rows_e = page.get("results") or []
                events.extend(rows_e)
                if not page.get("next") or not rows_e:
                    break
                offset += 200
                if offset > 2000:
                    break

        logger.info("bsd events %s..%s = %s", date_from, date_to, len(events))
        matched = 0
        fetched = 0
        for m in rows:
            ts = int(m["match_timestamp"] or 0)
            hit = None
            if apply:
                existing = get_event_map(m["match_id"])
                if existing:
                    hit = {
                        "bsd_event_id": existing["bsd_event_id"],
                        "home_team_id": existing.get("home_team_id"),
                        "away_team_id": existing.get("away_team_id"),
                        "confidence": existing.get("confidence"),
                    }
            if hit is None:
                hit = match_one(
                    m["home_team_name"], m["away_team_name"], ts, events, table,
                )
            dt = datetime.fromtimestamp(ts, CST).strftime("%m-%d %H:%M")
            if not hit:
                logger.info("NO  %s %s %s vs %s", dt, m.get("league_name"), m["home_team_name"], m["away_team_name"])
                continue
            matched += 1
            logger.info(
                "OK  %s %s %s vs %s -> %s (%s)",
                dt, m.get("league_name"), m["home_team_name"], m["away_team_name"],
                hit["bsd_event_id"], hit.get("confidence"),
            )
            if not apply:
                continue
            hit["jczq_home"] = m["home_team_name"]
            hit["jczq_away"] = m["away_team_name"]
            upsert_event_map(m["match_id"], hit)
            fetch_bundle(
                cache,
                int(hit["bsd_event_id"]),
                extra={"home_team_id": hit.get("home_team_id"), "away_team_id": hit.get("away_team_id")},
            )
            fetched += 1

        if apply:
            conn = db.get_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO bsd_sync_log
                          (date_from, date_to, jczq_n, matched_n, fetched_n, req_n)
                        VALUES (%s,%s,%s,%s,%s,%s)
                        """,
                        (date_from, date_to, len(rows), matched, fetched, client.req_n),
                    )
                conn.commit()
            finally:
                conn.close()
        logger.info("done matched=%s fetched=%s req=%s", matched, fetched, client.req_n)


def main(argv: Optional[List[str]] = None) -> None:
    p = argparse.ArgumentParser(description="BSD 赛前情报同步")
    p.add_argument("--apply", action="store_true", help="写 bsd_*（默认 dry-run）")
    p.add_argument("--days", type=int, default=3, help="未来几天在售场（默认 3）")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--kickoff-soon", action="store_true", help="只刷 2 小时内开球")
    args = p.parse_args(argv)
    sync(days=args.days, apply=args.apply, limit=args.limit, kickoff_soon=args.kickoff_soon)


if __name__ == "__main__":
    main()
