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


DDL += [
    """CREATE TABLE IF NOT EXISTS af_live_snapshots (
      id BIGINT AUTO_INCREMENT PRIMARY KEY,
      match_id VARCHAR(100) NOT NULL,
      af_fixture_id INT NOT NULL,
      captured_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '抓取时间(UTC)',
      odds_updated_at VARCHAR(32) NOT NULL DEFAULT '' COMMENT '接口给出的赔率更新时间(UTC ISO)',
      status VARCHAR(8) DEFAULT NULL,
      elapsed INT DEFAULT NULL,
      goals_home INT DEFAULT NULL,
      goals_away INT DEFAULT NULL,
      ah_line DECIMAL(5,2) DEFAULT NULL COMMENT '滚球亚盘主线,主队一侧,全场口径(负=主让)',
      ah_home DECIMAL(7,3) DEFAULT NULL,
      ah_away DECIMAL(7,3) DEFAULT NULL,
      ou_line DECIMAL(5,2) DEFAULT NULL,
      ou_over DECIMAL(7,3) DEFAULT NULL,
      ou_under DECIMAL(7,3) DEFAULT NULL,
      odds_json LONGTEXT COMMENT '亚盘/大小球/胜平负/总角球 各线原始值',
      stats_json TEXT COMMENT '双方技术统计(射门/角球/控球/xG 等)',
      UNIQUE KEY uk_snap (af_fixture_id, odds_updated_at, goals_home, goals_away, elapsed),
      KEY idx_match (match_id, captured_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
    """CREATE TABLE IF NOT EXISTS af_live_events (
      id BIGINT AUTO_INCREMENT PRIMARY KEY,
      match_id VARCHAR(100) NOT NULL,
      af_fixture_id INT NOT NULL,
      minute INT NOT NULL,
      extra_minute INT NOT NULL DEFAULT 0,
      type VARCHAR(24) NOT NULL,
      detail VARCHAR(64) NOT NULL DEFAULT '',
      team_id INT NOT NULL DEFAULT 0,
      player VARCHAR(96) NOT NULL DEFAULT '',
      assist VARCHAR(96) DEFAULT NULL,
      first_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '我们第一次抓到这条事件的时间(UTC), 用来量延迟',
      UNIQUE KEY uk_ev (af_fixture_id, minute, extra_minute, type, detail, team_id, player),
      KEY idx_match (match_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
]


def ensure_tables() -> None:
    with get_db() as conn:
        cur = conn.cursor()
        for sql in DDL:
            cur.execute(sql)
