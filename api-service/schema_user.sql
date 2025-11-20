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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_user_config (user_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户配置表';

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

