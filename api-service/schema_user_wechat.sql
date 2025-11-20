-- 微信小程序登录相关表结构修改
-- 在users表中添加微信相关字段

ALTER TABLE users 
ADD COLUMN IF NOT EXISTS openid VARCHAR(100) UNIQUE COMMENT '微信openid',
ADD COLUMN IF NOT EXISTS unionid VARCHAR(100) COMMENT '微信unionid',
ADD COLUMN IF NOT EXISTS wechat_nickname VARCHAR(100) COMMENT '微信昵称',
ADD COLUMN IF NOT EXISTS wechat_avatar VARCHAR(500) COMMENT '微信头像',
ADD COLUMN IF NOT EXISTS login_type VARCHAR(20) DEFAULT 'normal' COMMENT '登录类型: normal/wechat',
ADD INDEX idx_openid (openid);

