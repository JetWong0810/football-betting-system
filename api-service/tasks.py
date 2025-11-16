import logging
import threading
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler

import settings
from database import fetch_sync_status, init_db
from scraper.sporttery_service import SportterySyncService

logger = logging.getLogger(__name__)
_lock = threading.Lock()
_scheduler: Optional[BackgroundScheduler] = None


def run_sync_job() -> Optional[dict]:
    with _lock:
        service = SportterySyncService()
        try:
            stats = service.run_once()
            logger.info("Sync completed: %s", stats)
            return stats
        except Exception as exc:
            logger.exception("Sync failed: %s", exc)
            return None
        finally:
            service.close()


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler:
        return _scheduler
    init_db()
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_sync_job, "interval", seconds=settings.SYNC_INTERVAL_SECONDS, id="sporttery-sync", max_instances=1, coalesce=True)
    scheduler.start()
    _scheduler = scheduler
    return scheduler


def shutdown_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None


def get_sync_status():
    return fetch_sync_status()
