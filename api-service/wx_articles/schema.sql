-- 微信知社公众号文章(回调接收)。新增表,不改现有表。执行前需用户同意(本地库=生产库)。
CREATE TABLE IF NOT EXISTS wx_article (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    article_id VARCHAR(128) NOT NULL,          -- 知社文章唯一ID,去重键
    wxid VARCHAR(64) NOT NULL DEFAULT '',      -- 公众号id(gh_开头)
    account_name VARCHAR(128) NOT NULL DEFAULT '',
    title VARCHAR(512) NOT NULL DEFAULT '',
    description TEXT NULL,
    url VARCHAR(1024) NOT NULL DEFAULT '',
    cover VARCHAR(1024) NULL,
    publish_time DATETIME NULL,                -- 按北京时间解析
    content MEDIUMTEXT NULL,                   -- 纯文本正文,抓取失败为空
    raw_json MEDIUMTEXT NULL,                  -- 原始回调,便于字段变化时重解析
    status VARCHAR(16) NOT NULL DEFAULT 'pending',   -- pending|processing|done|failed
    attempts TINYINT NOT NULL DEFAULT 0,
    last_error VARCHAR(255) NULL,
    received_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_article (article_id),
    INDEX idx_status (status, id),
    INDEX idx_wx_pub (wxid, publish_time),
    INDEX idx_pub (publish_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
