"""竞彩场次 ↔ BSD event 对齐。"""
from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .aliases import TEAM_SEEDS
from . import db

logger = logging.getLogger(__name__)


def norm_en(s: str) -> Tuple[str, set]:
    s = unicodedata.normalize("NFKD", s or "")
    s = s.encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    drop = {"fc", "cf", "cd", "ud", "sc", "afc", "the", "de", "da", "do", "di", "of"}
    toks = [t for t in s.split() if t and t not in drop]
    return " ".join(toks), set(toks)


def load_alias_table() -> Dict[str, str]:
    out = {a: n for a, n in TEAM_SEEDS}
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT alias, bsd_name FROM bsd_team_map")
            for row in cur.fetchall() or []:
                alias, name = row.get("alias"), row.get("bsd_name")
                if alias and name and alias not in out:
                    out[alias] = name
    except Exception:
        logger.debug("bsd_team_map 读失败，仅用种子")
    finally:
        conn.close()
    return out


def cn_to_en(name: str, table: Dict[str, str]) -> Optional[str]:
    name = name or ""
    if name in table:
        return table[name]
    hits = [(k, v) for k, v in table.items() if k and k in name]
    hits.sort(key=lambda x: -len(x[0]))
    return hits[0][1] if hits else None


_CLUB = {"fc", "cf", "cd", "ud", "sc", "afc"}


def _raw_toks(s: str) -> set:
    s = unicodedata.normalize("NFKD", s or "")
    s = s.encode("ascii", "ignore").decode().lower()
    return set(re.findall(r"[a-z0-9]+", s))


def score_pair(cn: str, en: str, table: Dict[str, str]) -> float:
    mapped = cn_to_en(cn, table)
    n_en, t_en = norm_en(en)
    if not mapped:
        return 0.0
    n_m, t_m = norm_en(mapped)
    extra = _raw_toks(mapped) & _CLUB
    if extra and not extra <= _raw_toks(en):
        return 0.0
    if n_m and n_m == n_en:
        return 0.95
    if t_m and t_m <= t_en:
        return 0.90
    inter = t_m & t_en
    if inter:
        return 0.65 + 0.3 * len(inter) / max(len(t_m), 1)
    return 0.0


def event_ts(ev: Dict[str, Any]) -> int:
    s = ev.get("event_date") or ""
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return int(dt.timestamp())


def match_one(
    home: str,
    away: str,
    kickoff_ts: int,
    events: List[Dict[str, Any]],
    table: Dict[str, str],
    window_s: int = 1800,
) -> Optional[Dict[str, Any]]:
    scored = []
    for ev in events:
        try:
            ts = event_ts(ev)
        except Exception:
            continue
        dt = abs(ts - kickoff_ts)
        if dt > window_s:
            continue
        sh = score_pair(home, ev.get("home_team") or "", table)
        sa = score_pair(away, ev.get("away_team") or "", table)
        scored.append((sh + sa, min(sh, sa), -dt, sh, sa, ev.get("id"), ev))
    if not scored:
        return None
    scored.sort(reverse=True)
    best = scored[0]
    reason = None
    if best[3] >= 0.7 and best[4] >= 0.7:
        reason = "both"
    elif best[3] >= 0.85 or best[4] >= 0.85:
        close = [x for x in scored if x[0] >= best[0] - 0.2]
        if len(close) == 1:
            reason = "one-side-unique"
    if not reason:
        return None
    ev = best[6]
    return {
        "bsd_event_id": int(ev["id"]),
        "home_team_id": ev.get("home_team_id"),
        "away_team_id": ev.get("away_team_id"),
        "home_team": ev.get("home_team"),
        "away_team": ev.get("away_team"),
        "confidence": reason,
        "home_score": best[3],
        "away_score": best[4],
        "event": ev,
    }


def seed_team_map() -> int:
    conn = db.get_conn()
    n = 0
    try:
        with conn.cursor() as cur:
            for alias, name in TEAM_SEEDS:
                cur.execute(
                    """
                    INSERT INTO bsd_team_map (alias, bsd_name, source)
                    VALUES (%s,%s,'seed')
                    ON DUPLICATE KEY UPDATE
                      bsd_name=IF(source='seed', VALUES(bsd_name), bsd_name)
                    """,
                    (alias, name),
                )
                n += 1
        conn.commit()
    finally:
        conn.close()
    return n


def upsert_event_map(match_id: str, hit: Dict[str, Any]) -> None:
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bsd_event_map
                  (match_id, bsd_event_id, home_team_id, away_team_id, confidence)
                VALUES (%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                  bsd_event_id=VALUES(bsd_event_id),
                  home_team_id=VALUES(home_team_id),
                  away_team_id=VALUES(away_team_id),
                  confidence=VALUES(confidence),
                  mapped_at=CURRENT_TIMESTAMP
                """,
                (
                    match_id,
                    hit["bsd_event_id"],
                    hit.get("home_team_id"),
                    hit.get("away_team_id"),
                    hit.get("confidence") or "both",
                ),
            )
            for alias, tid, en in (
                (hit.get("jczq_home"), hit.get("home_team_id"), hit.get("home_team")),
                (hit.get("jczq_away"), hit.get("away_team_id"), hit.get("away_team")),
            ):
                if not alias:
                    continue
                cur.execute(
                    """
                    INSERT INTO bsd_team_map (alias, bsd_name, bsd_team_id, source)
                    VALUES (%s,%s,%s,'matched')
                    ON DUPLICATE KEY UPDATE
                      bsd_team_id=COALESCE(VALUES(bsd_team_id), bsd_team_id),
                      bsd_name=IF(source='seed', bsd_name, COALESCE(VALUES(bsd_name), bsd_name))
                    """,
                    (alias, en or alias, tid),
                )
        conn.commit()
    finally:
        conn.close()


def get_event_map(match_id: str) -> Optional[Dict[str, Any]]:
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM bsd_event_map WHERE match_id=%s", (match_id,))
            return cur.fetchone()
    finally:
        conn.close()
