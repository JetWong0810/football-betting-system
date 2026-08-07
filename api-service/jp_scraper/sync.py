#!/usr/bin/env python3
"""日本联赛数据同步入口。

用法:
  cd api-service
  python3 -m jp_scraper.sync --help
  python3 -m jp_scraper.sync --apply --schedule --years 2025,2026 --frames 1
  python3 -m jp_scraper.sync --apply --gekisaka
  python3 -m jp_scraper.sync --apply --cards --limit 30
  python3 -m jp_scraper.sync --apply --scorers --years 2025
  python3 -m jp_scraper.sync --apply --seed-aliases
  python3 -m jp_scraper.sync --apply --weather-today
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime
from typing import List, Optional

from . import aliases as alias_mod
from . import db
from .gekisaka import fetch_stamen_article, list_stamen_articles
from .http_client import JpHttp
from .match_card import fetch_match_card
from .schedule import FRAME_COMP, fetch_schedule
from .scorers import competition_label, fetch_top_scorers
from .weather import VENUE_COORDS, forecast_for_venue

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("jp_sync")


def seed_aliases(apply: bool) -> int:
    db.ensure_schema(apply=apply)
    if not apply:
        logger.info("dry-run seed aliases: %d clubs", len(alias_mod.J1_CLUB_SEEDS))
        return len(alias_mod.J1_CLUB_SEEDS)
    conn = db.get_conn()
    n = 0
    try:
        with conn.cursor() as cur:
            for short, slug, als, comp in alias_mod.J1_CLUB_SEEDS:
                cid = db.upsert_club(cur, short, slug=slug, competition=comp)
                db.upsert_alias(cur, short, cid, source="ja_short")
                for a in als:
                    db.upsert_alias(cur, a, cid, source="manual")
                    n += 1
        conn.commit()
        logger.info("seeded aliases for %d clubs, %d alias rows", len(alias_mod.J1_CLUB_SEEDS), n)
    finally:
        conn.close()
    return n


def sync_schedule(http: JpHttp, frames: List[int], years: List[int], apply: bool) -> int:
    db.ensure_schema(apply=apply)
    total = 0
    conn = db.get_conn() if apply else None
    try:
        for frame in frames:
            for year in years:
                rows = fetch_schedule(http, frame, year)
                logger.info("schedule frame=%s year=%s rows=%s", frame, year, len(rows))
                if not apply:
                    total += len(rows)
                    continue
                assert conn is not None
                with conn.cursor() as cur:
                    for r in rows:
                        home_id = db.upsert_club(
                            cur, r["home_short"], slug=r.get("home_slug"),
                            competition=FRAME_COMP.get(frame),
                        )
                        away_id = db.upsert_club(
                            cur, r["away_short"], slug=r.get("away_slug"),
                            competition=FRAME_COMP.get(frame),
                        )
                        venue_id = db.upsert_venue(cur, r.get("venue_short") or "")
                        mid = db.upsert_match(cur, {
                            "match_card_id": r.get("match_card_id"),
                            "season": r["season"],
                            "competition": r["competition"],
                            "competition_frame_id": frame,
                            "round_label": r.get("round_label"),
                            "kickoff_at": r.get("kickoff_at"),
                            "match_date": r.get("match_date"),
                            "home_club_id": home_id,
                            "away_club_id": away_id,
                            "venue_id": venue_id,
                            "home_score": r.get("home_score"),
                            "away_score": r.get("away_score"),
                            "status": r.get("status") or "scheduled",
                            "source_url": r.get("source_url"),
                        })
                        total += 1
                conn.commit()
                logger.info("upserted schedule frame=%s year=%s", frame, year)
    finally:
        if conn:
            conn.close()
    return total


def sync_cards(http: JpHttp, limit: int, apply: bool) -> int:
    """回填有 match_card_id 且缺 sfms02 阵容的比赛。"""
    db.ensure_schema(apply=apply)
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT m.jp_match_id, m.match_card_id, m.home_club_id, m.away_club_id
                FROM jp_matches m
                LEFT JOIN jp_lineups l ON l.jp_match_id=m.jp_match_id AND l.source='sfms02'
                WHERE m.match_card_id IS NOT NULL AND l.id IS NULL
                ORDER BY m.match_date DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
        logger.info("cards to fetch: %s", len(rows))
        if not apply:
            return len(rows)
        n = 0
        with conn.cursor() as cur:
            for row in rows:
                card_id = int(row["match_card_id"])
                try:
                    data = fetch_match_card(http, card_id)
                except Exception as e:
                    logger.warning("card %s fail: %s", card_id, e)
                    continue
                wx = data.get("weather") or {}
                if wx:
                    db.upsert_weather(cur, int(row["jp_match_id"]), "sfms02", **wx)
                for lu in data.get("lineups") or []:
                    club_id = row["home_club_id"] if lu["side"] == "home" else row["away_club_id"]
                    if not club_id:
                        continue
                    db.upsert_lineup(
                        cur, int(row["jp_match_id"]), int(club_id), lu["side"],
                        lu.get("players") or [], source="sfms02",
                        bench=lu.get("bench"), formation=lu.get("formation"),
                        source_url=data.get("source_url"),
                    )
                n += 1
                if n % 10 == 0:
                    conn.commit()
                    logger.info("cards progress %s/%s", n, len(rows))
        conn.commit()
        return n
    finally:
        conn.close()


def _resolve_club_by_hint(cur, hint: str) -> Optional[int]:
    hint = (hint or "").strip()
    if not hint:
        return None
    cur.execute("SELECT club_id FROM jp_team_aliases WHERE alias=%s", (hint,))
    row = cur.fetchone()
    if row:
        return int(row["club_id"])
    cur.execute("SELECT club_id FROM jp_clubs WHERE name_ja_short=%s", (hint,))
    row = cur.fetchone()
    if row:
        return int(row["club_id"])
    # 模糊: 简称包含 / 被包含
    cur.execute(
        "SELECT club_id, name_ja_short FROM jp_clubs WHERE %s LIKE CONCAT('%%', name_ja_short, '%%') "
        "OR name_ja_short LIKE %s LIMIT 5",
        (hint, f"%{hint}%"),
    )
    rows = cur.fetchall()
    if len(rows) == 1:
        return int(rows[0]["club_id"])
    return None


def sync_gekisaka(http: JpHttp, apply: bool) -> int:
    db.ensure_schema(apply=apply)
    articles = list_stamen_articles(http)
    logger.info("gekisaka stamen articles: %s", len(articles))
    for a in articles[:10]:
        logger.info("  %s", a["title"])
    if not apply:
        return len(articles)

    conn = db.get_conn()
    n_ok = 0
    try:
        with conn.cursor() as cur:
            for art in articles:
                try:
                    data = fetch_stamen_article(http, art["url"])
                except Exception as e:
                    logger.warning("gekisaka fetch fail %s: %s", art["url"], e)
                    continue
                home_hint = data.get("home_hint") or art.get("home_hint")
                away_hint = data.get("away_hint") or art.get("away_hint")
                home_id = _resolve_club_by_hint(cur, home_hint or "")
                away_id = _resolve_club_by_hint(cur, away_hint or "")
                if not home_id or not away_id:
                    logger.warning("skip unresolved teams %s vs %s", home_hint, away_hint)
                    continue
                # 今日或最近日期匹配
                today = date.today()
                cur.execute(
                    """
                    SELECT jp_match_id FROM jp_matches
                    WHERE home_club_id=%s AND away_club_id=%s
                      AND match_date BETWEEN %s AND %s
                    ORDER BY match_date DESC LIMIT 1
                    """,
                    (home_id, away_id, today.fromordinal(today.toordinal() - 1), today),
                )
                m = cur.fetchone()
                if not m:
                    # 尝试互换（标题主客与库不一致时）
                    cur.execute(
                        """
                        SELECT jp_match_id FROM jp_matches
                        WHERE home_club_id=%s AND away_club_id=%s
                          AND match_date BETWEEN %s AND %s
                        ORDER BY match_date DESC LIMIT 1
                        """,
                        (away_id, home_id, today.fromordinal(today.toordinal() - 1), today),
                    )
                    m = cur.fetchone()
                    if m:
                        home_id, away_id = away_id, home_id
                if not m:
                    logger.warning("no jp_match for %s vs %s", home_hint, away_hint)
                    continue
                mid = int(m["jp_match_id"])
                for lu in data.get("lineups") or []:
                    side = lu.get("side") or "home"
                    club_id = home_id if side == "home" else away_id
                    # 若 team_hint 能解析则覆盖
                    hint_id = _resolve_club_by_hint(cur, lu.get("team_hint") or "")
                    if hint_id in (home_id, away_id):
                        club_id = hint_id
                        side = "home" if club_id == home_id else "away"
                    db.upsert_lineup(
                        cur, mid, club_id, side, lu.get("players") or [],
                        source="gekisaka", bench=lu.get("bench"),
                        formation=lu.get("formation"),
                        source_url=data.get("source_url"), is_confirmed=1,
                    )
                n_ok += 1
                logger.info("gekisaka saved %s vs %s -> match %s", home_hint, away_hint, mid)
        conn.commit()
    finally:
        conn.close()
    return n_ok


def sync_scorers(http: JpHttp, years: List[int], frames: List[int], apply: bool) -> int:
    db.ensure_schema(apply=apply)
    total = 0
    conn = db.get_conn() if apply else None
    try:
        for frame in frames:
            for year in years:
                rows = fetch_top_scorers(http, frame, year_from=year, year_to=year)
                logger.info("scorers frame=%s year=%s n=%s", frame, year, len(rows))
                if not apply:
                    total += len(rows)
                    continue
                assert conn is not None
                with conn.cursor() as cur:
                    for r in rows:
                        club_id = None
                        if r.get("club_short"):
                            club_id = db.upsert_club(cur, r["club_short"], competition=FRAME_COMP.get(frame))
                        db.upsert_player_stat(
                            cur, season=str(year), competition=competition_label(frame),
                            player_name=r["player_name"], goals=r.get("goals"),
                            apps=r.get("apps"),
                            club_id=club_id, rank_no=r.get("rank_no"), source="sftd08",
                        )
                        total += 1
                conn.commit()
    finally:
        if conn:
            conn.close()
    return total


def sync_weather_today(apply: bool) -> int:
    db.ensure_schema(apply=apply)
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT m.jp_match_id, m.kickoff_at, v.name_ja AS venue
                FROM jp_matches m
                LEFT JOIN jp_venues v ON v.venue_id=m.venue_id
                WHERE m.match_date=%s AND m.status='scheduled'
                """,
                (date.today().isoformat(),),
            )
            rows = cur.fetchall()
        logger.info("weather candidates today: %s", len(rows))
        if not apply:
            return len(rows)
        n = 0
        with conn.cursor() as cur:
            for row in rows:
                venue = row.get("venue") or ""
                ko = row.get("kickoff_at")
                if not isinstance(ko, datetime):
                    continue
                # 补坐标到 venue
                if venue in VENUE_COORDS:
                    lat, lon = VENUE_COORDS[venue]
                    cur.execute(
                        "UPDATE jp_venues SET lat=%s, lon=%s WHERE name_ja=%s AND lat IS NULL",
                        (lat, lon, venue),
                    )
                fx = forecast_for_venue(venue, ko)
                if not fx:
                    logger.info("no coords for venue %s", venue)
                    continue
                db.upsert_weather(cur, int(row["jp_match_id"]), "open_meteo", **fx)
                n += 1
        conn.commit()
        return n
    finally:
        conn.close()


def link_jczq(apply: bool) -> int:
    """按别名+日期把 jp_matches 挂到竞彩 matches。"""
    db.ensure_schema(apply=apply)
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT m.jp_match_id, m.match_date, hc.name_ja_short AS home_s, ac.name_ja_short AS away_s
                FROM jp_matches m
                JOIN jp_clubs hc ON hc.club_id=m.home_club_id
                JOIN jp_clubs ac ON ac.club_id=m.away_club_id
                WHERE m.jczq_match_id IS NULL AND m.match_date IS NOT NULL
                """
            )
            jp_rows = cur.fetchall()
        logger.info("jp matches without jczq link: %s", len(jp_rows))
        if not apply:
            return len(jp_rows)
        n = 0
        with conn.cursor() as cur:
            for r in jp_rows:
                # 找别名集合
                cur.execute(
                    "SELECT alias FROM jp_team_aliases a JOIN jp_clubs c ON c.club_id=a.club_id "
                    "WHERE c.name_ja_short=%s",
                    (r["home_s"],),
                )
                home_aliases = [x["alias"] for x in cur.fetchall()] + [r["home_s"]]
                cur.execute(
                    "SELECT alias FROM jp_team_aliases a JOIN jp_clubs c ON c.club_id=a.club_id "
                    "WHERE c.name_ja_short=%s",
                    (r["away_s"],),
                )
                away_aliases = [x["alias"] for x in cur.fetchall()] + [r["away_s"]]
                cur.execute(
                    """
                    SELECT match_id, home_team_name, away_team_name FROM matches
                    WHERE match_date=%s
                      AND (league_name LIKE '日%%' OR league_name LIKE '%%天皇%%')
                    """,
                    (r["match_date"],),
                )
                cands = cur.fetchall()
                hit = None
                for c in cands:
                    hn, an = c["home_team_name"] or "", c["away_team_name"] or ""
                    if any(a in hn or hn in a for a in home_aliases) and any(
                        a in an or an in a for a in away_aliases
                    ):
                        hit = c["match_id"]
                        break
                if hit:
                    cur.execute(
                        "UPDATE jp_matches SET jczq_match_id=%s WHERE jp_match_id=%s",
                        (hit, r["jp_match_id"]),
                    )
                    n += 1
        conn.commit()
        logger.info("linked jczq matches: %s", n)
        return n
    finally:
        conn.close()


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="日本联赛免费数据同步")
    p.add_argument("--apply", action="store_true", help="写库（默认 dry-run）")
    p.add_argument("--seed-aliases", action="store_true")
    p.add_argument("--schedule", action="store_true")
    p.add_argument("--cards", action="store_true", help="回填 SFMS02 阵容/天气")
    p.add_argument("--gekisaka", action="store_true", help="临场スタメン")
    p.add_argument("--scorers", action="store_true")
    p.add_argument("--weather-today", action="store_true")
    p.add_argument("--link-jczq", action="store_true")
    p.add_argument("--years", default="2025,2026", help="逗号分隔年份")
    p.add_argument("--frames", default="1", help="competition_frame_id 逗号分隔, 1=J1")
    p.add_argument("--limit", type=int, default=50, help="cards 回填上限")
    p.add_argument("--all", action="store_true", help="别名+日程+ゲキサカ+天气+关联")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    years = [int(x) for x in args.years.split(",") if x.strip()]
    frames = [int(x) for x in args.frames.split(",") if x.strip()]
    apply = bool(args.apply)
    if not apply:
        logger.info("DRY-RUN mode (pass --apply to write)")

    run_all = args.all
    if run_all:
        args.seed_aliases = args.schedule = args.gekisaka = args.weather_today = args.link_jczq = True

    if not any([
        args.seed_aliases, args.schedule, args.cards, args.gekisaka,
        args.scorers, args.weather_today, args.link_jczq, run_all,
    ]):
        logger.error("请指定任务，例如 --all 或 --schedule --gekisaka")
        return 2

    db.ensure_schema(apply=apply)

    if args.seed_aliases:
        seed_aliases(apply)
    with JpHttp() as http:
        if args.schedule:
            sync_schedule(http, frames, years, apply)
        if args.cards:
            sync_cards(http, args.limit, apply)
        if args.gekisaka:
            sync_gekisaka(http, apply)
        if args.scorers:
            sync_scorers(http, years, frames, apply)
    if args.weather_today:
        sync_weather_today(apply)
    if args.link_jczq:
        link_jczq(apply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
