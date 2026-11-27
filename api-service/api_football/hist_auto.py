"""本赛季比赛库的后台增量同步: 每 6 小时取"昨天和今天"所有联赛的比赛, 把我们关心的联赛里新完赛、库里没有的场次抓详情入库,
并给新出现的球场补经纬度。每次约 2 次列表请求 + 新完赛场次/20 次详情请求。

没配 API_FOOTBALL_KEY 则不启动; MySQL GET_LOCK 防止多进程重复跑; 异常只记日志。
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timedelta

from database import get_db

logger = logging.getLogger(__name__)

INTERVAL = int(os.getenv("AF_HIST_INTERVAL_SEC", str(6 * 3600)))
DAYS_BACK = 2                      # 今天和前一天(比赛跨 UTC 日界、或延迟入库的场次也能补上)


def dates_to_sync(now: datetime = None, days_back: int = DAYS_BACK) -> list:
    now = now or datetime.utcnow()
    return [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days_back)]


def run_once() -> None:
    from . import geo, hist, schema
    from .client import AfClient
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT GET_LOCK('af_hist_loop', 0) AS ok")
        if not (cur.fetchone() or {}).get("ok"):
            return
        try:
            schema.ensure_tables()
            with AfClient() as c:
                r = hist.sync_dates(c, dates_to_sync())
                if r["saved"]:
                    logger.info("比赛库增量: 候选 %s 场, 新增 %s 场, 今日剩余额度 %s", r["candidates"], r["saved"], c.day_remaining)
            n = geo.geocode_pending(limit=100)
            if n:
                logger.info("比赛库: 新补坐标球场 %s 个", n)
        finally:
            cur.execute("SELECT RELEASE_LOCK('af_hist_loop')")


def _loop() -> None:
    time.sleep(120)
    while True:
        try:
            run_once()
        except Exception:  # noqa: BLE001
            logger.exception("比赛库增量同步异常")
        time.sleep(INTERVAL)


def start() -> None:
    if not (os.getenv("API_FOOTBALL_KEY") or "").strip():
        return
    threading.Thread(target=_loop, daemon=True, name="af-hist").start()
