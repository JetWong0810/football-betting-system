-- ============================================================
-- 清空测试用户数据脚本
-- 用途：清除所有用户相关的测试数据
-- 警告：此操作不可逆，请在测试环境确认无误后再在生产环境执行
-- ============================================================

-- 临时禁用外键检查
SET FOREIGN_KEY_CHECKS = 0;

-- 1. 清空用户下注记录
TRUNCATE TABLE user_bets;

-- 2. 清空用户配置
TRUNCATE TABLE user_configs;

-- 3. 清空用户表
TRUNCATE TABLE users;

-- 重新启用外键检查
SET FOREIGN_KEY_CHECKS = 1;

-- 验证清空结果
SELECT 'users' AS table_name, COUNT(*) AS remaining_rows FROM users
UNION ALL
SELECT 'user_configs', COUNT(*) FROM user_configs
UNION ALL
SELECT 'user_bets', COUNT(*) FROM user_bets;
