-- 第二批: 关联/事实/观点/公众号。全部新增表; 另给自建的 wx_article 加两列(表为空)。
ALTER TABLE wx_article
    ADD COLUMN summary VARCHAR(600) NULL AFTER content,
    ADD COLUMN analysis_json MEDIUMTEXT NULL AFTER summary,
    ADD COLUMN processed_at DATETIME NULL AFTER analysis_json;

CREATE TABLE IF NOT EXISTS wx_account (
    wxid VARCHAR(64) PRIMARY KEY,
    name VARCHAR(128) NOT NULL DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS wx_article_match (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    article_id BIGINT NOT NULL,                 -- wx_article.id
    match_id VARCHAR(64) NOT NULL,
    timing VARCHAR(16) NOT NULL DEFAULT 'preview',   -- preview(赛前) | review(赛后复盘)
    status VARCHAR(16) NOT NULL DEFAULT 'linked',    -- linked(两队命中) | ambiguous(存疑) | manual(手动)
    confidence TINYINT NOT NULL DEFAULT 0,
    evidence VARCHAR(255) NULL,                 -- 文中证明提到本场的原句
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_article_match (article_id, match_id),
    INDEX idx_match (match_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS wx_article_claim (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    article_id BIGINT NOT NULL,
    match_id VARCHAR(64) NULL,
    claim_type VARCHAR(16) NOT NULL DEFAULT 'other', -- injury|suspension|lineup|rotation|motivation|schedule|manager|odds|other
    side VARCHAR(8) NOT NULL DEFAULT 'both',         -- home|away|both
    subject VARCHAR(64) NOT NULL DEFAULT '',
    text VARCHAR(255) NOT NULL,
    quote VARCHAR(255) NOT NULL,                     -- 原文引用(已校验在正文中)
    verify_status VARCHAR(16) NOT NULL DEFAULT 'unverified', -- confirmed|contradicted|unverified
    verify_note VARCHAR(500) NULL,
    verify_sources TEXT NULL,                        -- JSON [{title,url,site,date}]
    impact_dir VARCHAR(8) NULL,                      -- upper|lower|neutral (AI评估,亚盘口径)
    impact_level VARCHAR(8) NULL,                    -- high|medium|low|none
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_article (article_id),
    INDEX idx_match (match_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS wx_article_pick (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    article_id BIGINT NOT NULL,
    wxid VARCHAR(64) NOT NULL DEFAULT '',
    match_id VARCHAR(64) NOT NULL,
    market VARCHAR(16) NOT NULL,        -- spf|rqspf|ah|ou|score|dc(双选/不败)|other
    line VARCHAR(16) NULL,              -- 盘口线(原文),如 -0.5 / 2.5
    selection VARCHAR(32) NOT NULL,     -- home|draw|away|home_draw|away_draw|over|under|其他原文
    quote VARCHAR(255) NOT NULL,
    pre_match TINYINT NOT NULL DEFAULT 1,            -- 发布时间早于开赛
    result VARCHAR(8) NOT NULL DEFAULT 'pending',    -- pending|hit|miss|push|void (仅此列赛后可更新)
    settled_at DATETIME NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_pick (article_id, match_id, market, selection),
    INDEX idx_wx (wxid, result),
    INDEX idx_match (match_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 第三批(倾向推测): 给自建的 wx_article_pick 加列。
-- ALTER TABLE wx_article_pick
--     ADD COLUMN basis VARCHAR(10) NOT NULL DEFAULT 'result' AFTER market,       -- result胜负 | handicap让球 | goals大小球 | score比分
--     ADD COLUMN explicit TINYINT NOT NULL DEFAULT 1 AFTER selection,            -- 1=作者明说 0=AI据文意推测
--     ADD COLUMN strength VARCHAR(8) NOT NULL DEFAULT 'medium' AFTER explicit,   -- strong|medium|weak(weak不计入命中率)
--     ADD COLUMN reasoning VARCHAR(255) NULL AFTER strength,                     -- 推断依据(≤40字)
--     ADD COLUMN line_source VARCHAR(8) NULL AFTER line;                         -- author | system
