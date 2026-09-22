-- BSD 赛前情报缓存（与竞彩赔率表分离）
-- 本地 MySQL = 生产库，仅 sync --apply / ensure_schema 时执行

CREATE TABLE IF NOT EXISTS bsd_http_cache (
  cache_key VARCHAR(512) NOT NULL,
  endpoint VARCHAR(256) NOT NULL,
  payload_json LONGTEXT,
  http_status INT NOT NULL DEFAULT 200,
  fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (cache_key),
  KEY idx_fetched (fetched_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS bsd_team_map (
  alias VARCHAR(128) NOT NULL COMMENT '竞彩中文名/简称',
  bsd_name VARCHAR(128) NOT NULL COMMENT '匹配用英文关键词',
  bsd_team_id INT DEFAULT NULL,
  source VARCHAR(40) NOT NULL DEFAULT 'seed',
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (alias),
  KEY idx_bsd_team (bsd_team_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS bsd_event_map (
  match_id VARCHAR(100) NOT NULL,
  bsd_event_id INT NOT NULL,
  home_team_id INT DEFAULT NULL,
  away_team_id INT DEFAULT NULL,
  confidence VARCHAR(32) NOT NULL DEFAULT 'both',
  mapped_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (match_id),
  KEY idx_bsd_event (bsd_event_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS bsd_sync_log (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  run_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  date_from VARCHAR(16) DEFAULT NULL,
  date_to VARCHAR(16) DEFAULT NULL,
  jczq_n INT DEFAULT 0,
  matched_n INT DEFAULT 0,
  fetched_n INT DEFAULT 0,
  req_n INT DEFAULT 0,
  note VARCHAR(512) DEFAULT NULL,
  KEY idx_run (run_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
