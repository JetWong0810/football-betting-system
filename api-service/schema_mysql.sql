-- MySQL Schema for Football Rational Betting Tracker

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
    home_team_name VARCHAR(200),
    home_team_rank VARCHAR(50),
    away_team_id VARCHAR(100),
    away_team_name VARCHAR(200),
    away_team_rank VARCHAR(50),
    is_single TINYINT DEFAULT 0,
    match_status VARCHAR(50),
    notice TEXT,
    odds_update_time VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_matches_date (match_date),
    INDEX idx_matches_league (league_name(100))
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
    home_score INT,
    away_score INT,
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

