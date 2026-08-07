"""DB helpers + schema ensure for jp_* tables."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pymysql

import settings

logger = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema_jp.sql"
_SCHEMA_READY = False


def get_conn():
    return pymysql.connect(
        **settings.MYSQL_CONFIG,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def ensure_schema(apply: bool = True) -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    if not apply:
        logger.info("dry-run: skip CREATE TABLE (%s)", SCHEMA_PATH.name)
        return
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # split on ; while keeping statements
            buf = []
            for line in sql.splitlines():
                s = line.strip()
                if not s or s.startswith("--"):
                    continue
                buf.append(line)
                if s.endswith(";"):
                    stmt = "\n".join(buf).strip().rstrip(";")
                    buf = []
                    if stmt:
                        cur.execute(stmt)
        conn.commit()
        _SCHEMA_READY = True
        logger.info("jp_* schema ready")
    finally:
        conn.close()


def upsert_club(cur, name_ja_short: str, slug: Optional[str] = None,
                competition: Optional[str] = None) -> int:
    name_ja_short = (name_ja_short or "").strip()
    if not name_ja_short:
        raise ValueError("empty club short name")
    cur.execute("SELECT club_id FROM jp_clubs WHERE name_ja_short=%s", (name_ja_short,))
    row = cur.fetchone()
    if row:
        cid = int(row["club_id"])
        if slug:
            cur.execute(
                "UPDATE jp_clubs SET slug=COALESCE(slug, %s), competition=COALESCE(competition, %s) WHERE club_id=%s",
                (slug, competition, cid),
            )
        return cid
    cur.execute(
        "INSERT INTO jp_clubs (slug, name_ja_short, competition) VALUES (%s,%s,%s)",
        (slug, name_ja_short, competition),
    )
    return int(cur.lastrowid)


def upsert_venue(cur, name_ja: str) -> Optional[int]:
    name_ja = (name_ja or "").strip()
    if not name_ja:
        return None
    cur.execute("SELECT venue_id FROM jp_venues WHERE name_ja=%s", (name_ja,))
    row = cur.fetchone()
    if row:
        return int(row["venue_id"])
    cur.execute("INSERT INTO jp_venues (name_ja) VALUES (%s)", (name_ja,))
    return int(cur.lastrowid)


def upsert_alias(cur, alias: str, club_id: int, source: str = "manual") -> None:
    alias = (alias or "").strip()
    if not alias:
        return
    cur.execute(
        "INSERT INTO jp_team_aliases (alias, club_id, source) VALUES (%s,%s,%s) "
        "ON DUPLICATE KEY UPDATE club_id=VALUES(club_id), source=VALUES(source)",
        (alias, club_id, source),
    )


def find_match_by_card(cur, match_card_id: int) -> Optional[Dict]:
    cur.execute("SELECT * FROM jp_matches WHERE match_card_id=%s", (match_card_id,))
    return cur.fetchone()


def find_match_by_teams_date(cur, home_club_id: int, away_club_id: int, match_date) -> Optional[Dict]:
    cur.execute(
        "SELECT * FROM jp_matches WHERE home_club_id=%s AND away_club_id=%s AND match_date=%s LIMIT 1",
        (home_club_id, away_club_id, match_date),
    )
    return cur.fetchone()


def upsert_match(cur, data: Dict[str, Any]) -> int:
    """按 match_card_id 或 (home,away,date) upsert，返回 jp_match_id。"""
    card = data.get("match_card_id")
    existing = None
    if card:
        existing = find_match_by_card(cur, int(card))
    if not existing and data.get("home_club_id") and data.get("away_club_id") and data.get("match_date"):
        existing = find_match_by_teams_date(
            cur, data["home_club_id"], data["away_club_id"], data["match_date"]
        )
    fields = [
        "match_card_id", "season", "competition", "competition_frame_id", "round_label",
        "kickoff_at", "match_date", "home_club_id", "away_club_id", "venue_id",
        "home_score", "away_score", "attendance", "status", "jczq_match_id", "source_url",
    ]
    if existing:
        mid = int(existing["jp_match_id"])
        sets = []
        vals = []
        for f in fields:
            if f in data and data[f] is not None:
                sets.append(f"{f}=%s")
                vals.append(data[f])
        if sets:
            vals.append(mid)
            cur.execute(f"UPDATE jp_matches SET {', '.join(sets)} WHERE jp_match_id=%s", vals)
        return mid
    cols = [f for f in fields if f in data]
    placeholders = ", ".join(["%s"] * len(cols))
    cur.execute(
        f"INSERT INTO jp_matches ({', '.join(cols)}) VALUES ({placeholders})",
        [data[f] for f in cols],
    )
    return int(cur.lastrowid)


def upsert_lineup(cur, jp_match_id: int, club_id: int, side: str, players: List[Dict],
                  source: str, bench: Optional[List] = None, formation: Optional[str] = None,
                  source_url: Optional[str] = None, is_confirmed: int = 1) -> None:
    cur.execute(
        """
        INSERT INTO jp_lineups
          (jp_match_id, club_id, side, formation, is_confirmed, players_json, bench_json, source, source_url)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
          formation=COALESCE(VALUES(formation), formation),
          is_confirmed=VALUES(is_confirmed),
          players_json=VALUES(players_json),
          bench_json=VALUES(bench_json),
          source_url=VALUES(source_url),
          fetched_at=CURRENT_TIMESTAMP
        """,
        (
            jp_match_id, club_id, side, formation, is_confirmed,
            json.dumps(players, ensure_ascii=False),
            json.dumps(bench or [], ensure_ascii=False),
            source, source_url,
        ),
    )


def upsert_weather(cur, jp_match_id: int, source: str, **kwargs) -> None:
    cur.execute(
        """
        INSERT INTO jp_match_weather
          (jp_match_id, weather_text, temp_c, humidity, precip_prob, wind_ms, source)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
          weather_text=COALESCE(VALUES(weather_text), weather_text),
          temp_c=COALESCE(VALUES(temp_c), temp_c),
          humidity=COALESCE(VALUES(humidity), humidity),
          precip_prob=COALESCE(VALUES(precip_prob), precip_prob),
          wind_ms=COALESCE(VALUES(wind_ms), wind_ms),
          fetched_at=CURRENT_TIMESTAMP
        """,
        (
            jp_match_id,
            kwargs.get("weather_text"),
            kwargs.get("temp_c"),
            kwargs.get("humidity"),
            kwargs.get("precip_prob"),
            kwargs.get("wind_ms"),
            source,
        ),
    )


def upsert_player_stat(cur, season: str, competition: str, player_name: str,
                       goals: Optional[int] = None, apps: Optional[int] = None,
                       club_id: Optional[int] = None, rank_no: Optional[int] = None,
                       source: str = "sftd08") -> None:
    cur.execute(
        """
        INSERT INTO jp_player_season_stats
          (season, competition, club_id, player_name, goals, apps, rank_no, source)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
          goals=COALESCE(VALUES(goals), goals),
          apps=COALESCE(VALUES(apps), apps),
          rank_no=COALESCE(VALUES(rank_no), rank_no),
          fetched_at=CURRENT_TIMESTAMP
        """,
        (season, competition, club_id, player_name, goals, apps, rank_no, source),
    )
