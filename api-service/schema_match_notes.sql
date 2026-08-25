-- 用户对单场比赛的个人分析备注(按 user_id + match_id 唯一)
CREATE TABLE IF NOT EXISTS match_personal_notes (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    match_id VARCHAR(64) NOT NULL COMMENT 'matches.match_id',
    content TEXT NOT NULL COMMENT '个人分析正文',
    rating TINYINT UNSIGNED NULL COMMENT '半星=1,满星=10',
    structure JSON NULL COMMENT '分类点选结构',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_user_match (user_id, match_id),
    INDEX idx_match_id (match_id),
    INDEX idx_user_updated (user_id, updated_at),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='比赛个人分析备注';
