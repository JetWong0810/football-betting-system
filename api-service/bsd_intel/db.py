"""bsd_* 连接与建表。"""
from __future__ import annotations

import logging
from pathlib import Path

import pymysql

import settings

logger = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
_SCHEMA_READY = False


def get_conn():
    return pymysql.connect(
        **settings.MYSQL_CONFIG,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def ensure_schema(apply: bool = True) -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    if not apply:
        logger.info("dry-run: skip CREATE TABLE (%s)", SCHEMA_PATH.name)
        return
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            buf = []
            for line in sql.splitlines():
                s = line.strip()
                if not s or s.startswith("--"):
                    continue
                buf.append(line)
                if s.endswith(";"):
                    stmt = "\n".join(buf).strip().rstrip(";")
                    buf = []
                    if stmt:
                        cur.execute(stmt)
        conn.commit()
        _SCHEMA_READY = True
        logger.info("bsd_* schema ready")
    finally:
        conn.close()
