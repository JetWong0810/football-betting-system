"""后台自动映射: 每 30 分钟对在售场次做一次竞彩 -> API-Football 映射(约 2~3 次请求)。

没配 API_FOOTBALL_KEY 则不启动; 用 MySQL GET_LOCK 防止多进程重复跑; 任何异常只记日志, 不影响 API。
"""
from __future__ import annotations

import logging
import os
import threading
import time

from database import get_db

logger = logging.getLogger(__name__)

INTERVAL = int(os.getenv("AF_MAP_INTERVAL_SEC", "1800"))


def run_once() -> None:
    from . import mapping, schema
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT GET_LOCK('af_map_loop', 0) AS ok")
        if not (cur.fetchone() or {}).get("ok"):
            return                                   # 别的进程正在跑
        try:
            schema.ensure_tables()
            r = mapping.run(apply=True)
            if r["todo"]:
                logger.info("API-Football 映射: 待映射 %s 场, 对上 %s, 未解决 %s, 今日剩余额度 %s",
                            r["todo"], len(r["matched"]), len(r["unresolved"]), r.get("day_remaining"))
                for x in r["unresolved"]:
                    logger.info("  未解决 %s", x)
        finally:
            cur.execute("SELECT RELEASE_LOCK('af_map_loop')")


def _loop() -> None:
    time.sleep(60)                                   # 让 API 先完成启动
    while True:
        try:
            run_once()
        except Exception:  # noqa: BLE001
            logger.exception("API-Football 自动映射异常")
        time.sleep(INTERVAL)


def start() -> None:
    if not (os.getenv("API_FOOTBALL_KEY") or "").strip():
        logger.info("未配置 API_FOOTBALL_KEY, 跳过 API-Football 自动映射")
        return
    threading.Thread(target=_loop, daemon=True, name="af-map").start()
