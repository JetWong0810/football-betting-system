#!/usr/bin/env python3
"""
Scraper service entrypoint - runs sync periodically in a loop.
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
from scraper.sporttery_service import SportterySyncService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

SYNC_INTERVAL = int(os.getenv("SYNC_INTERVAL_SECONDS", "600"))


def run_sync():
    service = SportterySyncService()
    try:
        logger.info("开始数据同步...")
        stats = service.run_once()
        logger.info(f"同步完成 - 比赛数: {stats.get('matches', 0)}, 赔率数: {stats.get('odds', 0)}")
        return stats
    except Exception as e:
        logger.exception(f"同步失败: {e}")
    finally:
        service.close()


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("足球竞彩数据抓取服务启动 (循环模式)")
    logger.info(f"同步间隔: {SYNC_INTERVAL} 秒")
    logger.info("=" * 60)

    init_db()
    logger.info("数据库初始化完成")

    while True:
        try:
            run_sync()
        except Exception as e:
            logger.error(f"本次同步异常: {e}")

        logger.info(f"等待 {SYNC_INTERVAL} 秒后进行下一次同步...")
        time.sleep(SYNC_INTERVAL)
