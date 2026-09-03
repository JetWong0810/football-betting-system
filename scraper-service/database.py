from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import pymysql

import settings

_SCHEMA_MYSQL = Path(settings.SCHEMA_MYSQL_PATH)


def init_db() -> None:
    """初始化数据库（仅 MySQL）"""
    _init_mysql_db()


def _init_mysql_db() -> None:
    """初始化 MySQL 数据库"""
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
                            if "already exists" not in str(e).lower() and "duplicate" not in str(e).lower():
                                print(f"警告: 执行 SQL 失败: {command[:50]}... {e}")
            # 为旧库补充比分/fid字段
            _ensure_match_columns(cursor)
            _ensure_fenxi_cache_table(cursor)
        conn.commit()
    finally:
        conn.close()


def _ensure_match_columns(cursor) -> None:
    """确保 matches 表有比分/fid_500/fid_zgzcw/sporttery_match_id 字段（兼容旧库）"""
    columns = {
        "home_score": "TINYINT DEFAULT NULL COMMENT '主队比分'",
        "away_score": "TINYINT DEFAULT NULL COMMENT '客队比分'",
        "fid_500": "VARCHAR(20) DEFAULT NULL COMMENT '500.com fixture id'",
        "fid_zgzcw": "VARCHAR(20) DEFAULT NULL COMMENT '足彩网 fenxi matchid'",
        "sporttery_match_id": "VARCHAR(32) DEFAULT NULL COMMENT '体彩官网 matchId'",
    }
    for col, definition in columns.items():
        cursor.execute(
            """
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME='matches' AND COLUMN_NAME=%s
            """,
            (col,),
        )
        exists = cursor.fetchone()
        count = exists[0] if isinstance(exists, (tuple, list)) else (exists.get("COUNT(*)") if isinstance(exists, dict) else 0)
        if not count:
            try:
                cursor.execute(f"ALTER TABLE matches ADD COLUMN {col} {definition}")
            except Exception as e:
                if "duplicate" not in str(e).lower():
                    print(f"警告: 添加字段 {col} 失败: {e}")


def _ensure_fenxi_cache_table(cursor) -> None:
    cursor.execute(
        """
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME='jczq_fenxi_cache'
        """
    )
    exists = cursor.fetchone()
    count = exists[0] if isinstance(exists, (tuple, list)) else (
        exists.get("COUNT(*)") if isinstance(exists, dict) else 0
    )
    if count:
        return
    cursor.execute(
        """
        CREATE TABLE jczq_fenxi_cache (
            match_id VARCHAR(100) PRIMARY KEY,
            asian_json MEDIUMTEXT,
            euro_json MEDIUMTEXT,
            form_json MEDIUMTEXT,
            asian_fetched_at DATETIME DEFAULT NULL,
            euro_fetched_at DATETIME DEFAULT NULL,
            form_fetched_at DATETIME DEFAULT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )


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
