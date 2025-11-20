-- 微信小程序登录相关表结构修改
-- 在users表中添加微信相关字段
-- 使用存储过程来安全地添加字段（如果不存在）

DELIMITER $$

-- 创建存储过程来添加字段（如果不存在）
DROP PROCEDURE IF EXISTS add_column_if_not_exists$$
CREATE PROCEDURE add_column_if_not_exists(
    IN table_name VARCHAR(64),
    IN column_name VARCHAR(64),
    IN column_definition TEXT
)
BEGIN
    DECLARE column_count INT DEFAULT 0;
    
    SELECT COUNT(*) INTO column_count
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = table_name
      AND COLUMN_NAME = column_name;
    
    IF column_count = 0 THEN
        SET @sql = CONCAT('ALTER TABLE ', table_name, ' ADD COLUMN ', column_name, ' ', column_definition);
        PREPARE stmt FROM @sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END$$

-- 创建存储过程来添加索引（如果不存在）
DROP PROCEDURE IF EXISTS add_index_if_not_exists$$
CREATE PROCEDURE add_index_if_not_exists(
    IN table_name VARCHAR(64),
    IN index_name VARCHAR(64),
    IN index_definition TEXT
)
BEGIN
    DECLARE index_count INT DEFAULT 0;
    
    SELECT COUNT(*) INTO index_count
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = table_name
      AND INDEX_NAME = index_name;
    
    IF index_count = 0 THEN
        SET @sql = CONCAT('ALTER TABLE ', table_name, ' ADD INDEX ', index_name, ' ', index_definition);
        PREPARE stmt FROM @sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END$$

DELIMITER ;

-- 添加微信相关字段
CALL add_column_if_not_exists('users', 'openid', 'VARCHAR(100) UNIQUE COMMENT ''微信openid''');
CALL add_column_if_not_exists('users', 'unionid', 'VARCHAR(100) COMMENT ''微信unionid''');
CALL add_column_if_not_exists('users', 'wechat_nickname', 'VARCHAR(100) COMMENT ''微信昵称''');
CALL add_column_if_not_exists('users', 'wechat_avatar', 'VARCHAR(500) COMMENT ''微信头像''');
CALL add_column_if_not_exists('users', 'login_type', 'VARCHAR(20) DEFAULT ''normal'' COMMENT ''登录类型: normal/wechat''');

-- 添加 openid 索引
CALL add_index_if_not_exists('users', 'idx_openid', '(openid)');

-- 清理存储过程
DROP PROCEDURE IF EXISTS add_column_if_not_exists;
DROP PROCEDURE IF EXISTS add_index_if_not_exists;
