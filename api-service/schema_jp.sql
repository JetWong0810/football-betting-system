-- 日本联赛本地库（免费抓取自 data.j-league / ゲキサカ / Open-Meteo）
-- 与竞彩表分离，前缀 jp_

CREATE TABLE IF NOT EXISTS jp_clubs (
  club_id INT AUTO_INCREMENT PRIMARY KEY,
  slug VARCHAR(64) DEFAULT NULL COMMENT 'jleague.jp club slug e.g. yokohamafm',
  name_ja_short VARCHAR(64) NOT NULL COMMENT '横浜FM / Ｇ大阪',
  name_ja VARCHAR(128) DEFAULT NULL,
  competition VARCHAR(16) DEFAULT NULL COMMENT 'J1/J2/J3',
  active TINYINT NOT NULL DEFAULT 1,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_short (name_ja_short),
  UNIQUE KEY uk_slug (slug),
  KEY idx_comp (competition)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS jp_team_aliases (
  alias VARCHAR(128) NOT NULL COMMENT '竞彩中文名等',
  club_id INT NOT NULL,
  source VARCHAR(40) DEFAULT 'manual',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (alias),
  KEY idx_club (club_id),
  CONSTRAINT fk_jp_alias_club FOREIGN KEY (club_id) REFERENCES jp_clubs(club_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS jp_venues (
  venue_id INT AUTO_INCREMENT PRIMARY KEY,
  name_ja VARCHAR(128) NOT NULL COMMENT 'MUFG国立 / パナスタ',
  name_full VARCHAR(256) DEFAULT NULL,
  lat DOUBLE DEFAULT NULL,
  lon DOUBLE DEFAULT NULL,
  city VARCHAR(64) DEFAULT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_venue (name_ja)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS jp_matches (
  jp_match_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  match_card_id INT DEFAULT NULL COMMENT 'SFMS02 match_card_id',
  season VARCHAR(16) NOT NULL COMMENT '2025 / 2026/27',
  competition VARCHAR(32) NOT NULL COMMENT 'J1/J2/联杯/天皇杯',
  competition_frame_id INT DEFAULT NULL,
  round_label VARCHAR(64) DEFAULT NULL COMMENT '第１節第１日',
  kickoff_at DATETIME DEFAULT NULL,
  match_date DATE DEFAULT NULL,
  home_club_id INT DEFAULT NULL,
  away_club_id INT DEFAULT NULL,
  venue_id INT DEFAULT NULL,
  home_score SMALLINT DEFAULT NULL,
  away_score SMALLINT DEFAULT NULL,
  attendance INT DEFAULT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'scheduled' COMMENT 'scheduled/finished',
  jczq_match_id VARCHAR(64) DEFAULT NULL,
  source_url VARCHAR(512) DEFAULT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_card (match_card_id),
  KEY idx_date (match_date),
  KEY idx_season_comp (season, competition),
  KEY idx_jczq (jczq_match_id),
  KEY idx_home (home_club_id),
  KEY idx_away (away_club_id),
  CONSTRAINT fk_jp_m_home FOREIGN KEY (home_club_id) REFERENCES jp_clubs(club_id),
  CONSTRAINT fk_jp_m_away FOREIGN KEY (away_club_id) REFERENCES jp_clubs(club_id),
  CONSTRAINT fk_jp_m_venue FOREIGN KEY (venue_id) REFERENCES jp_venues(venue_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS jp_lineups (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  jp_match_id BIGINT NOT NULL,
  club_id INT NOT NULL,
  side ENUM('home','away') NOT NULL,
  formation VARCHAR(32) DEFAULT NULL,
  is_confirmed TINYINT NOT NULL DEFAULT 1,
  players_json JSON NOT NULL COMMENT '[{num,name,pos}]',
  bench_json JSON DEFAULT NULL,
  source VARCHAR(32) NOT NULL COMMENT 'gekisaka|sfms02',
  source_url VARCHAR(512) DEFAULT NULL,
  fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_match_club_src (jp_match_id, club_id, source),
  KEY idx_match (jp_match_id),
  CONSTRAINT fk_jp_lu_match FOREIGN KEY (jp_match_id) REFERENCES jp_matches(jp_match_id),
  CONSTRAINT fk_jp_lu_club FOREIGN KEY (club_id) REFERENCES jp_clubs(club_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS jp_formations (
  jp_match_id BIGINT NOT NULL,
  home_formation VARCHAR(32) DEFAULT NULL,
  away_formation VARCHAR(32) DEFAULT NULL,
  source VARCHAR(32) NOT NULL DEFAULT 'jleague_jp',
  source_url VARCHAR(512) DEFAULT NULL,
  fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (jp_match_id),
  CONSTRAINT fk_jp_fm_match FOREIGN KEY (jp_match_id) REFERENCES jp_matches(jp_match_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS jp_player_season_stats (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  season VARCHAR(16) NOT NULL,
  competition VARCHAR(32) NOT NULL,
  club_id INT DEFAULT NULL,
  player_name VARCHAR(128) NOT NULL,
  goals INT DEFAULT NULL,
  apps INT DEFAULT NULL,
  rank_no INT DEFAULT NULL,
  source VARCHAR(32) NOT NULL DEFAULT 'sftd08',
  fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_player_season (season, competition, player_name, club_id),
  KEY idx_goals (season, competition, goals)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS jp_standings_snapshots (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  competition VARCHAR(32) NOT NULL,
  season VARCHAR(16) NOT NULL,
  as_of_date DATE NOT NULL,
  club_id INT NOT NULL,
  rank_no INT DEFAULT NULL,
  played INT DEFAULT NULL,
  pts INT DEFAULT NULL,
  gf INT DEFAULT NULL,
  ga INT DEFAULT NULL,
  form VARCHAR(16) DEFAULT NULL,
  fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_snap (competition, season, as_of_date, club_id),
  KEY idx_club (club_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS jp_suspensions (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  player_name VARCHAR(128) NOT NULL,
  club_id INT DEFAULT NULL,
  reason VARCHAR(256) DEFAULT NULL,
  from_date DATE DEFAULT NULL,
  to_date DATE DEFAULT NULL,
  notice_url VARCHAR(512) DEFAULT NULL,
  fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  KEY idx_player (player_name),
  KEY idx_club (club_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS jp_match_weather (
  jp_match_id BIGINT NOT NULL,
  weather_text VARCHAR(64) DEFAULT NULL COMMENT '晴/雨 官网',
  temp_c DOUBLE DEFAULT NULL,
  humidity INT DEFAULT NULL,
  precip_prob INT DEFAULT NULL COMMENT 'Open-Meteo 预报',
  wind_ms DOUBLE DEFAULT NULL,
  source VARCHAR(32) NOT NULL COMMENT 'sfms02|open_meteo',
  fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (jp_match_id, source),
  CONSTRAINT fk_jp_wx_match FOREIGN KEY (jp_match_id) REFERENCES jp_matches(jp_match_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS jp_match_events (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  jp_match_id BIGINT NOT NULL,
  club_id INT DEFAULT NULL,
  event_type VARCHAR(32) NOT NULL COMMENT 'goal|sub_out|sub_in|card',
  minute_label VARCHAR(16) DEFAULT NULL,
  player_name VARCHAR(128) DEFAULT NULL,
  player_name_2 VARCHAR(128) DEFAULT NULL COMMENT '换上球员',
  raw_json JSON DEFAULT NULL,
  KEY idx_match (jp_match_id),
  CONSTRAINT fk_jp_ev_match FOREIGN KEY (jp_match_id) REFERENCES jp_matches(jp_match_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
