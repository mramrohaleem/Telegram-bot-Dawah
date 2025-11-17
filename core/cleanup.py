from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta

from sqlalchemy.orm import sessionmaker

from config.settings import Settings
from core.logging_utils import get_logger, log_with_context
from storage.repositories import JobRepository

logger = get_logger(__name__)


def _safe_unlink(path: str) -> bool:
    try:
        os.remove(path)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        log_with_context(
            logger,
            level=logging.WARNING,
            message="Failed to delete file during cleanup",
            stage="CLEANUP",
            path=path,
        )
        return False


async def cleanup_loop(settings: Settings, session_factory: sessionmaker) -> None:
    """Periodically delete old temporary files for non-archived jobs."""

    if settings.tmp_retention_days is None or settings.tmp_retention_days <= 0:
        log_with_context(
            logger,
            level=logging.INFO,
            message="Cleanup loop disabled by configuration",
            stage="CLEANUP",
            tmp_retention_days=settings.tmp_retention_days,
        )
        return

    poll_interval = settings.cleanup_poll_interval_seconds
    retention_days = settings.tmp_retention_days

    log_with_context(
        logger,
        level=logging.INFO,
        message="Starting cleanup loop",
        stage="CLEANUP",
        tmp_retention_days=retention_days,
        poll_interval=poll_interval,
    )

    try:
        while True:
            try:
                await _cleanup_once(settings, session_factory)
            except Exception as exc:  # pragma: no cover - defensive
                log_with_context(
                    logger,
                    level=logging.ERROR,
                    message="Cleanup iteration failed",
                    stage="CLEANUP",
                    error=str(exc),
                )
            await asyncio.sleep(poll_interval)
    except asyncio.CancelledError:
        log_with_context(
            logger,
            level=logging.INFO,
            message="Cleanup loop cancelled",
            stage="CLEANUP",
        )
        raise


def _cleanup_once(settings: Settings, session_factory: sessionmaker) -> None:
    session = session_factory()
    try:
        repo = JobRepository(session)
        cutoff = datetime.utcnow() - timedelta(days=settings.tmp_retention_days or 0)
        candidates = repo.list_cleanup_candidates(cutoff=cutoff, limit=50)

        for job in candidates:
            file_path = job.file_path
            if not file_path:
                continue
            if not os.path.exists(file_path):
                job.file_path = None
                session.add(job)
                session.commit()
                continue

            if not os.path.abspath(file_path).startswith(os.path.abspath(settings.tmp_root)):
                log_with_context(
                    logger,
                    level=logging.WARNING,
                    message="Skipping cleanup for file outside tmp_root",
                    stage="CLEANUP",
                    job_id=job.id,
                    path=file_path,
                )
                continue

            deleted = _safe_unlink(file_path)
            if deleted:
                job.file_path = None
                session.add(job)
                session.commit()
                log_with_context(
                    logger,
                    level=logging.INFO,
                    message="Deleted old temporary file",
                    stage="CLEANUP",
                    job_id=job.id,
                    deleted_path=file_path,
                )
    finally:
        session.close()
