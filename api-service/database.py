from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import pymysql

import settings

_SCHEMA_MYSQL = Path(settings.SCHEMA_MYSQL_PATH)
_SCHEMA_USER = Path(settings.BASE_DIR) / "schema_user.sql"


def init_db() -> None:
    """初始化数据库（仅 MySQL）"""
    try:
        _init_mysql_db()
    except Exception as e:
        print(f"警告: 初始化比赛和赔率表失败: {e}")
        # 不抛出异常，允许服务继续启动
    
    try:
        _init_user_db()
    except Exception as e:
        print(f"警告: 初始化用户表失败: {e}")
        # 不抛出异常，允许服务继续启动


def _init_mysql_db() -> None:
    """初始化 MySQL 数据库（比赛和赔率表）"""
    conn = pymysql.connect(**settings.MYSQL_CONFIG)
    try:
        with conn.cursor() as cursor:
            with open(_SCHEMA_MYSQL, "r", encoding="utf-8") as f:
                sql_commands = f.read().split(";")
                for command in sql_commands:
                    command = command.strip()
                    if command:
                        try:
                            cursor.execute(command)
                        except Exception as e:
                            # 忽略已存在的表等错误，继续执行
                            if "already exists" not in str(e).lower() and "duplicate" not in str(e).lower():
                                print(f"警告: 执行 SQL 命令失败: {command[:50]}... 错误: {e}")
        conn.commit()
    finally:
        conn.close()


def _init_user_db() -> None:
    """初始化用户相关表"""
    if not _SCHEMA_USER.exists():
        print(f"警告: 用户表 SQL 文件不存在: {_SCHEMA_USER}")
        return  # 如果文件不存在，跳过（兼容旧版本）
    
    conn = pymysql.connect(**settings.MYSQL_CONFIG)
    try:
        with conn.cursor() as cursor:
            with open(_SCHEMA_USER, "r", encoding="utf-8") as f:
                sql_commands = f.read().split(";")
                for command in sql_commands:
                    command = command.strip()
                    if command:
                        try:
                            cursor.execute(command)
                        except Exception as e:
                            # 忽略已存在的表等错误，继续执行
                            if "already exists" not in str(e).lower() and "duplicate" not in str(e).lower():
                                print(f"警告: 执行 SQL 命令失败: {command[:50]}... 错误: {e}")
            # 追加微信登录相关字段，避免旧库缺失 openid/unionid 等导致 1054
            _ensure_wechat_columns(cursor)
        conn.commit()
    finally:
        conn.close()


def _add_column_if_missing(cursor, table: str, column: str, definition: str) -> None:
    """如果字段缺失则添加"""
    cursor.execute(
        """
        SELECT COUNT(*) AS cnt FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME=%s AND COLUMN_NAME=%s
        """,
        (table, column),
    )
    exists = cursor.fetchone()
    count = exists.get("cnt") if isinstance(exists, dict) else (exists[0] if exists else 0)
    if count:
        return
    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def _add_index_if_missing(cursor, table: str, index: str, definition: str) -> None:
    """如果索引缺失则添加"""
    cursor.execute(
        """
        SELECT COUNT(*) AS cnt FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME=%s AND INDEX_NAME=%s
        """,
        (table, index),
    )
    exists = cursor.fetchone()
    count = exists.get("cnt") if isinstance(exists, dict) else (exists[0] if exists else 0)
    if count:
        return
    cursor.execute(f"ALTER TABLE {table} ADD INDEX {index} {definition}")


def _ensure_wechat_columns(cursor) -> None:
    """确保微信登录相关字段存在"""
    try:
        _add_column_if_missing(cursor, "users", "openid", "VARCHAR(100) UNIQUE COMMENT '微信openid'")
        _add_column_if_missing(cursor, "users", "unionid", "VARCHAR(100) COMMENT '微信unionid'")
        _add_column_if_missing(cursor, "users", "wechat_nickname", "VARCHAR(100) COMMENT '微信昵称'")
        _add_column_if_missing(cursor, "users", "wechat_avatar", "VARCHAR(500) COMMENT '微信头像'")
        _add_column_if_missing(cursor, "users", "login_type", "VARCHAR(20) DEFAULT 'normal' COMMENT '登录类型: normal/wechat'")
        _add_index_if_missing(cursor, "users", "idx_openid", "(openid)")
    except Exception as e:
        print(f"警告: 自动添加微信字段失败: {e}")


def _connect():
    """连接 MySQL 数据库"""
    return pymysql.connect(
        **settings.MYSQL_CONFIG,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


@contextmanager
def get_db():
    """获取数据库连接的上下文管理器"""
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _execute(conn, sql: str, params=None) -> Any:
    """执行 MySQL 查询"""
    cursor = conn.cursor()
    try:
        cursor.execute(sql, params or ())
        return cursor
    except Exception:
        cursor.close()
        raise


def touch_sync_status(conn) -> None:
    """确保 sync_status 表有记录"""
    with conn.cursor() as cursor:
        cursor.execute(
            "INSERT IGNORE INTO sync_status (id, last_synced_at, total_matches, total_odds) VALUES (1, NULL, 0, 0)"
        )


def update_sync_status(conn, total_matches: int, total_odds: int) -> None:
    """更新同步状态"""
    now = datetime.utcnow().isoformat()
    touch_sync_status(conn)
    
    with conn.cursor() as cursor:
        cursor.execute(
            "UPDATE sync_status SET last_synced_at = %s, total_matches = %s, total_odds = %s WHERE id = 1",
            (now, total_matches, total_odds),
        )


def fetch_sync_status() -> Dict[str, Any]:
    """获取同步状态"""
    with get_db() as conn:
        touch_sync_status(conn)
        
        with conn.cursor() as cursor:
            cursor.execute("SELECT last_synced_at, total_matches, total_odds FROM sync_status WHERE id = 1")
            row = cursor.fetchone()
            if row:
                return row
        
        return {"last_synced_at": None, "total_matches": 0, "total_odds": 0}
