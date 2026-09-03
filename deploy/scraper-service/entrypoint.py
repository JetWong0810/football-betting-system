#!/usr/bin/env python3
"""
Scraper service entrypoint - runs sync periodically in a loop.
临近开赛缩短间隔、只打体彩赔率, 避免 10 分钟一轮错过封盘前最后变动。
"""
import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
load_dotenv()

from database import init_db
from scraper.sporttery_service import (
    SportterySyncService,
    compute_sync_sleep,
    should_light_sync,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

SYNC_INTERVAL = int(os.getenv("SYNC_INTERVAL_SECONDS", "600"))


def run_sync():
    service = SportterySyncService()
    try:
        eta = service.seconds_until_next_kickoff()
        light = should_light_sync(eta)
        logger.info(
            "开始数据同步..."
            + (f" 下场开赛 {int(eta)}s" if eta is not None else " 无未开赛场")
            + (" [轻量]" if light else "")
        )
        stats = service.run_once(light=light)
        eta_after = service.seconds_until_next_kickoff()
        logger.info(
            f"同步完成 - 比赛数: {stats.get('matches', 0)}, 赔率数: {stats.get('odds', 0)}, "
            f"回填比分: {stats.get('scores', 0)}, 亚盘: {stats.get('asian', 0)}"
        )
        return stats, eta_after
    except Exception as e:
        logger.exception(f"同步失败: {e}")
        return None, None
    finally:
        service.close()


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("足球竞彩数据抓取服务启动 (循环模式)")
    logger.info(f"常规间隔: {SYNC_INTERVAL} 秒; 开赛前自动加密体彩赔率")
    logger.info("=" * 60)

    init_db()
    logger.info("数据库初始化完成")

    while True:
        try:
            _, eta = run_sync()
        except Exception as e:
            logger.error(f"本次同步异常: {e}")
            eta = None

        sleep_s = compute_sync_sleep(eta, full_interval=SYNC_INTERVAL)
        if eta is not None and eta > 0:
            logger.info(f"距下场开赛 {int(eta)} 秒, 等待 {sleep_s} 秒后同步...")
        else:
            logger.info(f"等待 {sleep_s} 秒后进行下一次同步...")
        time.sleep(sleep_s)
