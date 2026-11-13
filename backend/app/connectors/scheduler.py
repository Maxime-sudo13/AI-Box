"""Synchronisations planifiées : chaque minute, les connexions dont l'intervalle est écoulé sont
synchronisées, une par une, chacune dans sa propre session."""

import logging
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.models import Connection

from .registry import CONNECTORS
from .sync import SyncBusy, run_sync

logger = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None


def due_connections(db, now: datetime) -> list[Connection]:
    offline = get_settings().offline_mode
    connections = db.scalars(select(Connection).where(Connection.status.in_(("active", "error")))).all()
    return [
        c
        for c in connections
        if c.connector in CONNECTORS
        and not (offline and CONNECTORS[c.connector].online)
        and (c.last_sync_at is None or c.last_sync_at <= now - timedelta(minutes=c.interval_minutes))
    ]


def tick() -> None:
    with SessionLocal() as db:
        for connection in due_connections(db, datetime.now(UTC)):
            try:
                run_sync(db, connection, "schedule")
            except SyncBusy:
                continue
            except Exception:
                logger.exception("Synchronisation planifiée en échec")


def start() -> None:
    global _scheduler
    if _scheduler is None and get_settings().scheduler_enabled:
        _scheduler = BackgroundScheduler(timezone="UTC")
        _scheduler.add_job(tick, "interval", minutes=1, id="connectors", max_instances=1, coalesce=True)
        from app.ops.backup import scheduled_backup

        _scheduler.add_job(scheduled_backup, "cron", hour=get_settings().backup_hour, minute=30, id="backup",
                           max_instances=1, coalesce=True)  # fmt: skip
        _scheduler.start()


def running() -> bool:
    return _scheduler is not None and _scheduler.running


def next_backup():
    job = _scheduler.get_job("backup") if _scheduler else None
    return job.next_run_time if job else None


def stop() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
