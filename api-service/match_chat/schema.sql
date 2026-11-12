-- 同赔页「一场一会话」AI 分析聊天记录。新增表,不改现有表。
-- 注意: 本地库=生产库,执行前需用户明确同意。
CREATE TABLE IF NOT EXISTS match_chat_messages (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    match_id VARCHAR(64) NOT NULL,
    role VARCHAR(16) NOT NULL,                 -- user | assistant
    content MEDIUMTEXT NOT NULL,
    verdict_json TEXT NULL,                    -- assistant 的结构化结论(盘路方向/置信/依据/风险),供赛后复盘
    sources_json TEXT NULL,                    -- 联网来源 [{title,url}]
    attachments_n TINYINT NOT NULL DEFAULT 0,  -- 用户附带的图片数(图片本身不落库)
    web_used TINYINT NOT NULL DEFAULT 0,
    ctx_hash CHAR(16) NULL,                    -- 本轮所用系统数据指纹
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_match (user_id, match_id, id),
    INDEX idx_match (match_id, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
