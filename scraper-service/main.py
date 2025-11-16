#!/usr/bin/env python3
"""
足球竞彩数据抓取服务
用于从外部API抓取比赛和赔率数据，并存储到MySQL数据库
"""
import logging
import sys
from pathlib import Path
from dotenv import load_dotenv

# 添加当前目录到 Python 路径
sys.path.insert(0, str(Path(__file__).resolve().parent))

from database import init_db
from scraper.sporttery_service import SportterySyncService

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 加载环境变量
load_dotenv()


def run_sync():
    """执行一次数据同步"""
    service = SportterySyncService()
    try:
        logger.info("开始数据同步...")
        stats = service.run_once()
        logger.info(f"同步完成 - 比赛数: {stats.get('matches', 0)}, 赔率数: {stats.get('odds', 0)}")
        return stats
    except Exception as e:
        logger.exception(f"同步失败: {e}")
        raise
    finally:
        service.close()


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("足球竞彩数据抓取服务启动")
    logger.info("=" * 60)
    
    try:
        # 初始化数据库
        init_db()
        logger.info("数据库初始化完成")
        
        # 执行数据同步
        stats = run_sync()
        
        logger.info("=" * 60)
        logger.info("数据同步任务完成")
        logger.info(f"统计信息:")
        logger.info(f"  - 同步比赛数: {stats.get('matches', 0)}")
        logger.info(f"  - 同步赔率数: {stats.get('odds', 0)}")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error("=" * 60)
        logger.error("数据同步失败")
        logger.error(f"错误信息: {e}")
        logger.error("=" * 60)
        sys.exit(1)

