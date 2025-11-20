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
        conn.commit()
    finally:
        conn.close()


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
