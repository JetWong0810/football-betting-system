-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE,
    phone VARCHAR(20) UNIQUE,
    email VARCHAR(100) UNIQUE,
    password_hash VARCHAR(255) COMMENT '普通登录密码，微信登录可为空',
    nickname VARCHAR(100),
    avatar VARCHAR(500),
    openid VARCHAR(100) UNIQUE COMMENT '微信openid',
    unionid VARCHAR(100) COMMENT '微信unionid',
    wechat_nickname VARCHAR(100) COMMENT '微信昵称',
    wechat_avatar VARCHAR(500) COMMENT '微信头像',
    login_type VARCHAR(20) DEFAULT 'normal' COMMENT '登录类型: normal/wechat',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    last_login_at TIMESTAMP NULL,
    status TINYINT DEFAULT 1 COMMENT '1:正常 0:禁用',
    INDEX idx_username (username),
    INDEX idx_phone (phone),
    INDEX idx_email (email),
    INDEX idx_openid (openid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户表';

-- 用户配置表（存储用户的策略设置）
CREATE TABLE IF NOT EXISTS user_configs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    starting_capital DECIMAL(10,2) DEFAULT 10000.00 COMMENT '初始资金',
    fixed_ratio DECIMAL(5,4) DEFAULT 0.0300 COMMENT '固定比例',
    kelly_factor DECIMAL(5,4) DEFAULT 0.5000 COMMENT '凯利调整系数',
    stop_loss_limit INT DEFAULT 3 COMMENT '止损次数',
    target_monthly_return DECIMAL(5,4) DEFAULT 0.1000 COMMENT '月度盈利目标',
    theme VARCHAR(20) DEFAULT 'light' COMMENT '主题',
    risk_tolerance VARCHAR(20) DEFAULT 'balanced' COMMENT '风险策略等级',
    profit_aggressive_ratio DECIMAL(5,4) DEFAULT 0.5000 COMMENT '盈利金计入有效资金的比例',
    withdraw_threshold DECIMAL(5,4) DEFAULT 0.3000 COMMENT '出金阀阈值(盈利金/本金)',
    withdraw_ratio DECIMAL(5,4) DEFAULT 0.5000 COMMENT '触发后建议提取盈利金的比例',
    realized_withdraw DECIMAL(10,2) DEFAULT 0.00 COMMENT '已提取落袋的盈利',
    cool_hours INT DEFAULT 2 COMMENT '连不中暂停后冷静时长(小时)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_user_config (user_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户配置表';

-- 迁移：给已有 user_configs 表增加 risk_tolerance 列
ALTER TABLE user_configs ADD COLUMN risk_tolerance VARCHAR(20) DEFAULT 'balanced' COMMENT '风险策略等级' AFTER theme;

-- 迁移：资金分层与控手相关列
ALTER TABLE user_configs ADD COLUMN profit_aggressive_ratio DECIMAL(5,4) DEFAULT 0.5000 COMMENT '盈利金计入有效资金的比例' AFTER risk_tolerance;
ALTER TABLE user_configs ADD COLUMN withdraw_threshold DECIMAL(5,4) DEFAULT 0.3000 COMMENT '出金阀阈值(盈利金/本金)' AFTER profit_aggressive_ratio;
ALTER TABLE user_configs ADD COLUMN withdraw_ratio DECIMAL(5,4) DEFAULT 0.5000 COMMENT '触发后建议提取盈利金的比例' AFTER withdraw_threshold;
ALTER TABLE user_configs ADD COLUMN realized_withdraw DECIMAL(10,2) DEFAULT 0.00 COMMENT '已提取落袋的盈利' AFTER withdraw_ratio;
ALTER TABLE user_configs ADD COLUMN cool_hours INT DEFAULT 2 COMMENT '连不中暂停后冷静时长(小时)' AFTER realized_withdraw;

-- 比赛个人分析备注（关联用户 + match_id）
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

-- 用户投注记录表（关联用户）
CREATE TABLE IF NOT EXISTS user_bets (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    bet_data JSON NOT NULL COMMENT '投注记录JSON数据',
    bet_time TIMESTAMP NOT NULL COMMENT '投注时间',
    status VARCHAR(20) DEFAULT 'saved' COMMENT 'saved/betting/settled',
    result VARCHAR(20) COMMENT 'win/lose/pending/half-win/half-lose',
    stake DECIMAL(10,2) NOT NULL COMMENT '投注金额',
    odds DECIMAL(10,2) NOT NULL COMMENT '赔率',
    profit DECIMAL(10,2) COMMENT '盈亏',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id),
    INDEX idx_bet_time (bet_time),
    INDEX idx_status (status),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户投注记录表';

