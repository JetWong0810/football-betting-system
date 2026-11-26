"""API-Football 映射表(新建表, 不改动任何已有表)。"""
from __future__ import annotations

from database import get_db

DDL = [
    """CREATE TABLE IF NOT EXISTS af_team_map (
      alias VARCHAR(128) NOT NULL COMMENT '竞彩/北单中文队名(与 matches 里的写法一致)',
      af_team_id INT NOT NULL,
      af_name VARCHAR(128) NOT NULL,
      source VARCHAR(24) NOT NULL DEFAULT 'learned' COMMENT 'learned=比赛配对自动学到 / manual=人工指定',
      updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      PRIMARY KEY (alias),
      KEY idx_af_team (af_team_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
    """CREATE TABLE IF NOT EXISTS af_fixture_map (
      match_id VARCHAR(100) NOT NULL,
      af_fixture_id INT NOT NULL,
      af_league_id INT DEFAULT NULL,
      af_season INT DEFAULT NULL,
      af_home_id INT DEFAULT NULL,
      af_away_id INT DEFAULT NULL,
      method VARCHAR(24) NOT NULL COMMENT 'both/fuzzy/one_side/manual',
      confidence DECIMAL(4,2) NOT NULL DEFAULT 0,
      mapped_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      PRIMARY KEY (match_id),
      KEY idx_af_fixture (af_fixture_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
]


DDL += [
    """CREATE TABLE IF NOT EXISTS af_injuries_cache (
      match_id VARCHAR(100) NOT NULL,
      af_fixture_id INT NOT NULL,
      payload_json LONGTEXT,
      fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (match_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
    """CREATE TABLE IF NOT EXISTS af_squad_cache (
      af_team_id INT NOT NULL,
      payload_json LONGTEXT,
      fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (af_team_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
]


def ensure_tables() -> None:
    with get_db() as conn:
        cur = conn.cursor()
        for sql in DDL:
            cur.execute(sql)
