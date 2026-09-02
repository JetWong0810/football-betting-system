#!/usr/bin/env python3
"""一次性修复：按北京墙钟重算 match_timestamp，并回填缺比分场次。

用法（scraper-service 目录，连生产库需谨慎）:
  python3 repair_kickoff_ts.py
  python3 repair_kickoff_ts.py --dry-run
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone

from database import get_db
from repository import OddsRepository
from scraper.score_sporttery import clear_cache, fetch_ft_scores
from scraper.sporttery_service import beijing_kickoff_ts, derive_sale_date

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("repair_kickoff_ts")

_BJ = timezone(timedelta(hours=8))


def repair_timestamps(dry_run: bool) -> int:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT match_id, match_date, match_time, match_timestamp, "
            "home_team_name, away_team_name FROM matches "
            "WHERE match_date IS NOT NULL AND match_time IS NOT NULL "
            "AND match_time != ''"
        )
        rows = list(cur.fetchall())

    updates = []
    for r in rows:
        correct = beijing_kickoff_ts(str(r["match_date"]), str(r["match_time"]))
        if correct is None:
            continue
        old = r.get("match_timestamp")
        if old == correct:
            continue
        updates.append((correct, r["match_id"], r, old))

    for i, (correct, mid, r, old) in enumerate(updates):
        if i < 15 or mid == "2040656":
            old_s = (
                datetime.fromtimestamp(old, _BJ).strftime("%Y-%m-%d %H:%M")
                if old
                else None
            )
            new_s = datetime.fromtimestamp(correct, _BJ).strftime("%Y-%m-%d %H:%M")
            logger.info(
                "ts %s %s vs %s: %s -> %s (%s -> %s)",
                mid,
                r["home_team_name"],
                r["away_team_name"],
                old,
                correct,
                old_s,
                new_s,
            )

    if not dry_run and updates:
        with get_db() as conn:
            cur = conn.cursor()
            cur.executemany(
                "UPDATE matches SET match_timestamp=%s, updated_at=CURRENT_TIMESTAMP "
                "WHERE match_id=%s",
                [(correct, mid) for correct, mid, _, _ in updates],
            )
    logger.info("timestamp mismatches: %s (dry_run=%s)", len(updates), dry_run)
    return len(updates)


def backfill_scores(dry_run: bool) -> int:
    repo = OddsRepository()
    pending = repo.get_finished_without_score(days=7)
    logger.info("pending without score: %s", len(pending))
    if not pending:
        return 0
    dates = [str(m.get("match_date") or "")[:10] for m in pending if m.get("match_date")]
    clear_cache()
    scores = fetch_ft_scores(min(dates), max(dates)) if dates else {}
    updated = 0
    for m in pending:
        score = scores.get(str(m.get("match_id") or "").strip())
        if not score:
            continue
        updated += 1
        logger.info(
            "score %s %s %s:%s %s",
            m.get("match_id"),
            m.get("home_team_name"),
            score[0],
            score[1],
            m.get("away_team_name"),
        )
        if not dry_run:
            repo.update_match_score(m["match_id"], score[0], score[1])
    logger.info("scores backfilled: %s (dry_run=%s)", updated, dry_run)
    return updated


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    repair_timestamps(args.dry_run)
    backfill_scores(args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
