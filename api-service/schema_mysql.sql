-- MySQL Schema for Football Betting System

CREATE TABLE IF NOT EXISTS matches (
    match_id VARCHAR(100) PRIMARY KEY,
    match_number VARCHAR(50),
    match_code VARCHAR(50),
    project_type VARCHAR(50) DEFAULT 'football',
    league_id VARCHAR(100),
    league_name VARCHAR(200),
    league_full_name VARCHAR(300),
    match_date VARCHAR(20),
    match_time VARCHAR(20),
    match_timestamp BIGINT,
    home_team_id VARCHAR(100),
    home_team_id_500 VARCHAR(32) DEFAULT NULL COMMENT '500.com team id 主队',
    home_team_name VARCHAR(200),
    home_team_rank VARCHAR(50),
    away_team_id VARCHAR(100),
    away_team_id_500 VARCHAR(32) DEFAULT NULL COMMENT '500.com team id 客队',
    away_team_name VARCHAR(200),
    away_team_rank VARCHAR(50),
    is_single TINYINT DEFAULT 0,
    match_status VARCHAR(50),
    notice TEXT,
    odds_update_time VARCHAR(50),
    fid_500 VARCHAR(20) DEFAULT NULL COMMENT '500.com fixture id',
    fid_zgzcw VARCHAR(20) DEFAULT NULL COMMENT '足彩网 fenxi matchid',
    sporttery_match_id VARCHAR(32) DEFAULT NULL COMMENT '体彩官网 matchId',
    home_score TINYINT DEFAULT NULL,
    away_score TINYINT DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_matches_date (match_date),
    INDEX idx_matches_league (league_name(100)),
    UNIQUE KEY uk_sporttery_match_id (sporttery_match_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS odds_win_draw_lose (
    id INT AUTO_INCREMENT PRIMARY KEY,
    match_id VARCHAR(100) NOT NULL,
    odds_type VARCHAR(50) NOT NULL,
    handicap DECIMAL(10,2) DEFAULT 0,
    win_odds DECIMAL(10,2),
    draw_odds DECIMAL(10,2),
    lose_odds DECIMAL(10,2),
    win_support DECIMAL(10,2),
    draw_support DECIMAL(10,2),
    lose_support DECIMAL(10,2),
    is_single TINYINT DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_match_odds (match_id, odds_type),
    INDEX idx_odds_wdl_match (match_id),
    FOREIGN KEY (match_id) REFERENCES matches(match_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS odds_correct_score (
    id INT AUTO_INCREMENT PRIMARY KEY,
    match_id VARCHAR(100) NOT NULL,
    result_type VARCHAR(50) NOT NULL,
    home_score INT NOT NULL DEFAULT -1,
    away_score INT NOT NULL DEFAULT -1,
    score_label VARCHAR(50),
    odds DECIMAL(10,2),
    is_other TINYINT DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_match_score (match_id, result_type, home_score, away_score, is_other),
    INDEX idx_odds_score_match (match_id),
    FOREIGN KEY (match_id) REFERENCES matches(match_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS odds_total_goals (
    id INT AUTO_INCREMENT PRIMARY KEY,
    match_id VARCHAR(100) NOT NULL,
    goal_range VARCHAR(50) NOT NULL,
    min_goals INT,
    max_goals INT,
    odds DECIMAL(10,2),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_match_goals (match_id, goal_range),
    INDEX idx_odds_goals_match (match_id),
    FOREIGN KEY (match_id) REFERENCES matches(match_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS odds_half_full_time (
    id INT AUTO_INCREMENT PRIMARY KEY,
    match_id VARCHAR(100) NOT NULL,
    half_result VARCHAR(10) NOT NULL,
    full_result VARCHAR(10) NOT NULL,
    result_label VARCHAR(50),
    odds DECIMAL(10,2),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_match_hafu (match_id, half_result, full_result),
    INDEX idx_odds_hafu_match (match_id),
    FOREIGN KEY (match_id) REFERENCES matches(match_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS sync_status (
    id INT PRIMARY KEY CHECK (id = 1),
    last_synced_at VARCHAR(50),
    total_matches INT DEFAULT 0,
    total_odds INT DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS jczq_fenxi_cache (
    match_id VARCHAR(100) PRIMARY KEY,
    asian_json MEDIUMTEXT,
    euro_json MEDIUMTEXT,
    form_json MEDIUMTEXT,
    ou_json MEDIUMTEXT,
    asian_fetched_at DATETIME DEFAULT NULL,
    euro_fetched_at DATETIME DEFAULT NULL,
    form_fetched_at DATETIME DEFAULT NULL,
    ou_fetched_at DATETIME DEFAULT NULL,
    ticks_fetched_at DATETIME DEFAULT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS jczq_ah_ticks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    match_id VARCHAR(100) NOT NULL,
    company VARCHAR(50) NOT NULL DEFAULT 'Bet365',
    cid INT NOT NULL DEFAULT 2,
    tick_time DATETIME NOT NULL,
    home_odds DECIMAL(8,3) DEFAULT NULL,
    handicap DECIMAL(6,2) DEFAULT NULL COMMENT '500原值 正=主让',
    handicap_text VARCHAR(32) DEFAULT NULL,
    away_odds DECIMAL(8,3) DEFAULT NULL,
    UNIQUE KEY uk_match_company_time (match_id, company, tick_time),
    INDEX idx_match_company (match_id, company)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS prediction_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    match_id VARCHAR(100) NOT NULL,
    predict_type VARCHAR(20) NOT NULL DEFAULT 'worldcup' COMMENT 'worldcup or normal',
    direction VARCHAR(10) NOT NULL COMMENT 'upper/lower/neutral',
    confidence INT NOT NULL DEFAULT 50,
    overall_reverse TINYINT(1) NOT NULL DEFAULT 0,
    handicap DECIMAL(5,2) COMMENT '预测时的盘口',
    factors_json JSON COMMENT '完整因子快照',
    analysis TEXT COMMENT 'AI分析文本',
    predicted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_match_type (match_id, predict_type),
    INDEX idx_pred_match (match_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 500.com 球队身份（匹配主键）+ 体彩对照
CREATE TABLE IF NOT EXISTS teams_500 (
    team_id VARCHAR(32) PRIMARY KEY,
    primary_name VARCHAR(200) NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS team_aliases_500 (
    team_id VARCHAR(32) NOT NULL,
    alias VARCHAR(200) NOT NULL,
    source VARCHAR(40) DEFAULT 'shuju',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (team_id, alias),
    INDEX idx_alias (alias)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS team_id_map (
    sporttery_team_id VARCHAR(100) NOT NULL,
    team_id_500 VARCHAR(32) NOT NULL,
    evidence_match_id VARCHAR(100) DEFAULT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (sporttery_team_id, team_id_500),
    INDEX idx_map_500 (team_id_500)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
