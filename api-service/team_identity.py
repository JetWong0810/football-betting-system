"""500.com 球队身份：team_id 主键 + 别名 + 体彩对照。

匹配权威在 500 侧；体彩 home_team_id 仅作 bridge。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Set

from database import get_db, _add_column_if_missing

logger = logging.getLogger(__name__)

_SCHEMA_READY = False


def ensure_team_identity_schema() -> None:
    """建薄表 + matches 上补 500 team_id 字段（幂等）。"""
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS teams_500 (
                        team_id VARCHAR(32) PRIMARY KEY,
                        primary_name VARCHAR(200) NOT NULL,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                            ON UPDATE CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                      COLLATE=utf8mb4_unicode_ci
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS team_aliases_500 (
                        team_id VARCHAR(32) NOT NULL,
                        alias VARCHAR(200) NOT NULL,
                        source VARCHAR(40) DEFAULT 'shuju',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (team_id, alias),
                        INDEX idx_alias (alias)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                      COLLATE=utf8mb4_unicode_ci
                    """
                )
                # FK 可选：旧库若 teams_500 后建，避免 ALTER 失败；不强制 FK
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS team_id_map (
                        sporttery_team_id VARCHAR(100) NOT NULL,
                        team_id_500 VARCHAR(32) NOT NULL,
                        evidence_match_id VARCHAR(100) DEFAULT NULL,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                            ON UPDATE CURRENT_TIMESTAMP,
                        PRIMARY KEY (sporttery_team_id, team_id_500),
                        INDEX idx_map_500 (team_id_500)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                      COLLATE=utf8mb4_unicode_ci
                    """
                )
                _add_column_if_missing(
                    cur,
                    "matches",
                    "home_team_id_500",
                    "home_team_id_500 VARCHAR(32) DEFAULT NULL "
                    "COMMENT '500.com team id 主队' AFTER home_team_id",
                )
                _add_column_if_missing(
                    cur,
                    "matches",
                    "away_team_id_500",
                    "away_team_id_500 VARCHAR(32) DEFAULT NULL "
                    "COMMENT '500.com team id 客队' AFTER away_team_id",
                )
        _SCHEMA_READY = True
    except Exception as e:
        logger.warning(f"ensure_team_identity_schema 失败: {e}")


def _norm_alias(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    s = str(name).strip()
    return s or None


def merge_alias_lists(*groups: Optional[Sequence[str]]) -> List[str]:
    """去重别名，长名优先。"""
    out: List[str] = []
    for g in groups:
        if not g:
            continue
        for raw in g:
            s = _norm_alias(raw)
            if s and s not in out:
                out.append(s)
    return sorted(out, key=len, reverse=True)


def get_aliases_for_team(team_id_500: Optional[str]) -> List[str]:
    """从 DB 读该 500 球队的全部已知别名。"""
    if not team_id_500:
        return []
    ensure_team_identity_schema()
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT primary_name FROM teams_500 WHERE team_id=%s",
                    (str(team_id_500),),
                )
                row = cur.fetchone()
                names: List[str] = []
                if row and row.get("primary_name"):
                    names.append(row["primary_name"])
                cur.execute(
                    "SELECT alias FROM team_aliases_500 WHERE team_id=%s",
                    (str(team_id_500),),
                )
                for r in cur.fetchall() or []:
                    a = r.get("alias")
                    if a and a not in names:
                        names.append(a)
                return merge_alias_lists(names)
    except Exception as e:
        logger.warning(f"get_aliases_for_team({team_id_500}) 失败: {e}")
        return []


def enrich_match_data_aliases(match_data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """把 DB 已沉淀别名并入 match_data 的 home/awayTeamAliases。"""
    if not match_data:
        return match_data
    for side, id_key, alias_key in (
        ("home", "homeTeamId", "homeTeamAliases"),
        ("away", "awayTeamId", "awayTeamAliases"),
    ):
        tid = match_data.get(id_key)
        page_aliases = match_data.get(alias_key) or []
        db_aliases = get_aliases_for_team(tid) if tid else []
        merged = merge_alias_lists(page_aliases, db_aliases)
        if merged:
            match_data[alias_key] = merged
    return match_data


def upsert_team_identity(
    *,
    home_team_id_500: Optional[str],
    away_team_id_500: Optional[str],
    home_aliases: Optional[Sequence[str]] = None,
    away_aliases: Optional[Sequence[str]] = None,
    home_primary: Optional[str] = None,
    away_primary: Optional[str] = None,
    sporttery_home_id: Optional[str] = None,
    sporttery_away_id: Optional[str] = None,
    match_id: Optional[str] = None,
) -> None:
    """写入 teams_500 / aliases / sporttery↔500 map，并可选回写 matches。"""
    ensure_team_identity_schema()
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                _upsert_one_team(
                    cur,
                    team_id=home_team_id_500,
                    primary=home_primary,
                    aliases=home_aliases,
                    sporttery_id=sporttery_home_id,
                    match_id=match_id,
                    source="shuju",
                )
                _upsert_one_team(
                    cur,
                    team_id=away_team_id_500,
                    primary=away_primary,
                    aliases=away_aliases,
                    sporttery_id=sporttery_away_id,
                    match_id=match_id,
                    source="shuju",
                )
                if match_id and (home_team_id_500 or away_team_id_500):
                    cur.execute(
                        """
                        UPDATE matches
                        SET home_team_id_500 = COALESCE(%s, home_team_id_500),
                            away_team_id_500 = COALESCE(%s, away_team_id_500)
                        WHERE match_id = %s
                        """,
                        (home_team_id_500, away_team_id_500, match_id),
                    )
    except Exception as e:
        logger.warning(f"upsert_team_identity 失败 match={match_id}: {e}")


def upsert_from_match_data(
    match_id: str,
    match: Dict[str, Any],
    match_data: Dict[str, Any],
) -> None:
    """predict 路径：从 fetch_match_data 结果沉淀身份。"""
    if not match_data:
        return
    upsert_team_identity(
        home_team_id_500=_norm_alias(match_data.get("homeTeamId")),
        away_team_id_500=_norm_alias(match_data.get("awayTeamId")),
        home_aliases=match_data.get("homeTeamAliases"),
        away_aliases=match_data.get("awayTeamAliases"),
        home_primary=_norm_alias(match_data.get("homeTeamName")),
        away_primary=_norm_alias(match_data.get("awayTeamName")),
        sporttery_home_id=_norm_alias(match.get("home_team_id")),
        sporttery_away_id=_norm_alias(match.get("away_team_id")),
        match_id=match_id,
    )


def _upsert_one_team(
    cur,
    *,
    team_id: Optional[str],
    primary: Optional[str],
    aliases: Optional[Sequence[str]],
    sporttery_id: Optional[str],
    match_id: Optional[str],
    source: str,
) -> None:
    if not team_id:
        return
    tid = str(team_id)
    alias_set: Set[str] = set()
    for a in aliases or []:
        n = _norm_alias(a)
        if n:
            alias_set.add(n)
    prim = _norm_alias(primary)
    if not prim:
        prim = next(iter(sorted(alias_set, key=len, reverse=True)), None)
    if not prim:
        prim = tid
    if prim:
        alias_set.add(prim)

    cur.execute(
        """
        INSERT INTO teams_500 (team_id, primary_name)
        VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE
            primary_name = IF(CHAR_LENGTH(VALUES(primary_name)) >= CHAR_LENGTH(primary_name),
                              VALUES(primary_name), primary_name)
        """,
        (tid, prim),
    )
    for alias in alias_set:
        cur.execute(
            """
            INSERT IGNORE INTO team_aliases_500 (team_id, alias, source)
            VALUES (%s, %s, %s)
            """,
            (tid, alias, source),
        )
    if sporttery_id:
        cur.execute(
            """
            INSERT INTO team_id_map (sporttery_team_id, team_id_500, evidence_match_id)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
                evidence_match_id = COALESCE(VALUES(evidence_match_id), evidence_match_id)
            """,
            (str(sporttery_id), tid, match_id),
        )
