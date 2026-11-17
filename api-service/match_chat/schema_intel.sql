-- 单场情报(联网搜集,所有用户共享)。新增表,不改现有表。
-- 注意: 本地库=生产库,执行前需用户明确同意。
CREATE TABLE IF NOT EXISTS match_intel (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    match_id VARCHAR(64) NOT NULL,
    side VARCHAR(8) NOT NULL DEFAULT 'neutral',      -- home | away | neutral
    category VARCHAR(8) NOT NULL DEFAULT '其他',      -- 伤停|阵容|战意|赛程|数据|教练|其他
    text VARCHAR(255) NOT NULL,                      -- 客观陈述,不含预测
    source VARCHAR(64) NOT NULL DEFAULT '',          -- 站点名
    source_url VARCHAR(500) NULL,                    -- 仅保留确实出现在搜索结果里的链接
    pub_date VARCHAR(10) NULL,                       -- MM-DD 或 YYYY-MM-DD
    status VARCHAR(10) NOT NULL DEFAULT 'pending',   -- confirmed(官方或多源一致) | pending(单源)
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_match (match_id, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 每场的情报搜集记录(无结果也记一条,避免每次进入都重复联网)
CREATE TABLE IF NOT EXISTS match_intel_run (
    match_id VARCHAR(64) PRIMARY KEY,
    n INT NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
