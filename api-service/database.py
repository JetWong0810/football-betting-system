import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import pymysql

import settings

_DB_PATH = Path(settings.SQLITE_PATH)
_SCHEMA = Path(settings.SCHEMA_PATH)
_SCHEMA_MYSQL = Path(settings.SCHEMA_MYSQL_PATH)


def init_db() -> None:
    """初始化数据库"""
    if settings.DB_TYPE == "mysql":
        _init_mysql_db()
    else:
        _init_sqlite_db()


def _init_sqlite_db() -> None:
    """初始化 SQLite 数据库"""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    try:
        with open(_SCHEMA, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
    finally:
        conn.close()


def _init_mysql_db() -> None:
    """初始化 MySQL 数据库"""
    conn = pymysql.connect(**settings.MYSQL_CONFIG)
    try:
        with conn.cursor() as cursor:
            with open(_SCHEMA_MYSQL, "r", encoding="utf-8") as f:
                # 分割SQL语句并逐个执行
                sql_commands = f.read().split(';')
                for command in sql_commands:
                    command = command.strip()
                    if command:
                        cursor.execute(command)
        conn.commit()
    finally:
        conn.close()


def _connect_sqlite() -> sqlite3.Connection:
    """连接 SQLite 数据库"""
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _connect_mysql():
    """连接 MySQL 数据库"""
    conn = pymysql.connect(
        **settings.MYSQL_CONFIG,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False
    )
    return conn


def _connect():
    """根据配置连接数据库"""
    if settings.DB_TYPE == "mysql":
        return _connect_mysql()
    else:
        return _connect_sqlite()


@contextmanager
def get_db():
    """获取数据库连接的上下文管理器"""
    conn = _connect()
    try:
        if settings.DB_TYPE == "mysql":
            yield conn
            conn.commit()
        else:
            yield conn
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _execute_sqlite(conn: sqlite3.Connection, sql: str, params=None) -> Any:
    """执行 SQLite 查询"""
    if params:
        return conn.execute(sql, params)
    return conn.execute(sql)


def _execute_mysql(conn, sql: str, params=None) -> Any:
    """执行 MySQL 查询"""
    with conn.cursor() as cursor:
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        return cursor


def _execute(conn, sql: str, params=None) -> Any:
    """根据数据库类型执行查询"""
    if settings.DB_TYPE == "mysql":
        return _execute_mysql(conn, sql, params)
    else:
        return _execute_sqlite(conn, sql, params)


def touch_sync_status(conn) -> None:
    """确保 sync_status 表有记录"""
    if settings.DB_TYPE == "mysql":
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT IGNORE INTO sync_status (id, last_synced_at, total_matches, total_odds) VALUES (1, NULL, 0, 0)"
            )
    else:
        conn.execute(
            "INSERT OR IGNORE INTO sync_status (id, last_synced_at, total_matches, total_odds) VALUES (1, NULL, 0, 0)"
        )


def update_sync_status(conn, total_matches: int, total_odds: int) -> None:
    """更新同步状态"""
    now = datetime.utcnow().isoformat()
    touch_sync_status(conn)
    
    if settings.DB_TYPE == "mysql":
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE sync_status SET last_synced_at = %s, total_matches = %s, total_odds = %s WHERE id = 1",
                (now, total_matches, total_odds),
            )
    else:
        conn.execute(
            "UPDATE sync_status SET last_synced_at = ?, total_matches = ?, total_odds = ? WHERE id = 1",
            (now, total_matches, total_odds),
        )


def fetch_sync_status() -> Dict[str, Any]:
    """获取同步状态"""
    with get_db() as conn:
        touch_sync_status(conn)
        
        if settings.DB_TYPE == "mysql":
            with conn.cursor() as cursor:
                cursor.execute("SELECT last_synced_at, total_matches, total_odds FROM sync_status WHERE id = 1")
                row = cursor.fetchone()
                if row:
                    return row
        else:
            cur = conn.execute("SELECT last_synced_at, total_matches, total_odds FROM sync_status WHERE id = 1")
            row = cur.fetchone()
            if row:
                return dict(row)
        
        return {"last_synced_at": None, "total_matches": 0, "total_odds": 0}
