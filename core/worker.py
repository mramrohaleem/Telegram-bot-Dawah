"""Async worker loop for scheduling and processing jobs."""
from __future__ import annotations

import asyncio
import os
import logging
from datetime import datetime

from sqlalchemy.orm import Session, sessionmaker

from config.settings import Settings
from core.archive import maybe_archive_job_file
from core.logging_utils import get_logger, log_with_context
from core.state_machine import (
    mark_job_completed,
    mark_job_failed,
    mark_job_queued,
    mark_job_running,
)
from download.base import DownloadError
from download.engine import DownloadEngine
from core.job_service import update_job_progress
from storage.models import ErrorType, Job, JobStatus, JobType, SourceType
from storage.repositories import AuthProfileRepository, ChatSettingsRepository, JobRepository

logger = get_logger(__name__)
_engine = DownloadEngine()


def _classify_processing_exception(exc: Exception) -> ErrorType:
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        return ErrorType.NETWORK_ERROR
    return ErrorType.INTERNAL_ERROR


async def worker_loop(settings: Settings, session_factory: sessionmaker[Session]) -> None:
    """Continuously schedule and process jobs using the download engine."""

    log_with_context(
        logger,
        level=logging.INFO,
        message="Worker loop started",
        stage="WORKER",
        max_parallel_jobs=settings.max_parallel_jobs,
        max_queue_length=settings.max_queue_length,
        poll_interval=settings.worker_poll_interval_seconds,
    )

    try:
        while True:
            try:
                await _schedule_pending_jobs(settings, session_factory)
                await _start_jobs_from_queue(settings, session_factory)
            except Exception as exc:  # pragma: no cover - defensive guard
                log_with_context(
                    logger,
                    level=logging.ERROR,
                    message="Worker loop iteration failed",
                    stage="WORKER",
                    error=str(exc),
                )
            await asyncio.sleep(settings.worker_poll_interval_seconds)
    except asyncio.CancelledError:
        log_with_context(
            logger, level=logging.INFO, message="Worker loop cancelled", stage="WORKER"
        )
        raise


async def _schedule_pending_jobs(
    settings: Settings, session_factory: sessionmaker[Session]
) -> None:
    session = session_factory()
    try:
        repo = JobRepository(session)
        queued_count = repo.count_jobs_by_status(JobStatus.QUEUED)
        capacity = settings.max_queue_length - queued_count
        if capacity <= 0:
            log_with_context(
                logger,
                level=logging.INFO,
                message="Queue is full, skipping scheduling new jobs",
                stage="QUEUE",
                queued=queued_count,
                max_queue_length=settings.max_queue_length,
            )
            return

        pending_jobs = repo.list_jobs_by_status(JobStatus.PENDING, limit=capacity)
        for job in pending_jobs:
            _safe_mark_queued(session, job)
    except Exception:
        session.rollback()
        logger.exception("Unexpected error while scheduling pending jobs")
    finally:
        session.close()


async def _start_jobs_from_queue(
    settings: Settings, session_factory: sessionmaker[Session]
) -> None:
    session = session_factory()
    try:
        repo = JobRepository(session)
        running_count = repo.count_jobs_by_status(JobStatus.RUNNING)
        capacity = settings.max_parallel_jobs - running_count
        if capacity <= 0:
            log_with_context(
                logger,
                level=logging.INFO,
                message="Max parallel jobs reached, not starting more jobs",
                stage="WORKER",
                running=running_count,
                max_parallel_jobs=settings.max_parallel_jobs,
            )
            return

        queued_jobs = repo.list_jobs_by_status(JobStatus.QUEUED, limit=capacity)
        for job in queued_jobs:
            transitioned = _safe_mark_running(session, job)
            if transitioned:
                asyncio.create_task(_process_job(settings, session_factory, job.id))
    except Exception:
        session.rollback()
        logger.exception("Unexpected error while starting queued jobs")
    finally:
        session.close()


def _safe_mark_queued(session: Session, job: Job) -> Job | None:
    try:
        return mark_job_queued(session, job, metadata={"reason": "scheduled"})
    except Exception:
        session.rollback()
        log_with_context(
            logger,
            level=logging.ERROR,
            message="Failed to transition job to QUEUED",
            stage="QUEUE",
            job_id=job.id,
        )
        return None


def _safe_mark_running(session: Session, job: Job) -> Job | None:
    try:
        return mark_job_running(session, job, metadata={"reason": "worker_start"})
    except Exception:
        session.rollback()
        log_with_context(
            logger,
            level=logging.ERROR,
            message="Failed to transition job to RUNNING",
            stage="WORKER",
            job_id=job.id,
        )
        return None


async def _process_job(
    settings: Settings, session_factory: sessionmaker[Session], job_id: int
) -> None:
    session = session_factory()
    repo = JobRepository(session)
    chat_settings_repo = ChatSettingsRepository(session)
    try:
        job = repo.get_by_id(job_id)
        if job is None:
            log_with_context(
                logger,
                level=logging.ERROR,
                message="Job not found when starting processing",
                stage="WORKER",
                job_id=job_id,
            )
            return

        try:
            source_type = SourceType(job.source_type)
        except ValueError:
            source_type = SourceType.GENERIC
        try:
            job_type = JobType(job.job_type)
        except ValueError:
            job_type = JobType.VIDEO
        if settings.mock_downloads:
            log_with_context(
                logger,
                level=logging.INFO,
                message="Processing job (mock)",
                stage="WORKER",
                job_id=job.id,
            )

            await asyncio.sleep(1.0)

            mock_dir = os.path.join(settings.tmp_root, "mock")
            os.makedirs(mock_dir, exist_ok=True)
            job.file_path = os.path.join(mock_dir, f"{job.id}.dat")
            maybe_archive_job_file(
                settings=settings,
                job_repo=repo,
                chat_settings_repo=chat_settings_repo,
                job=job,
            )
            mark_job_completed(session, job, metadata={"mock": True})
            return

        log_with_context(
            logger,
            level=logging.INFO,
            message="Starting download for job",
            stage="WORKER",
            job_id=job.id,
            source_type=job.source_type,
            url=job.url,
        )

        auth_repo = AuthProfileRepository(session)
        auth_profile = None
        if job.auth_profile_id:
            auth_profile = auth_repo.get_by_id(job.auth_profile_id)
        if auth_profile is None:
            auth_profile = auth_repo.get_preferred_profile_for_source(source_type)

        cookie_file = auth_profile.cookie_file_path if auth_profile else None
        target_dir = os.path.join(settings.tmp_root, str(job.id))
        max_filesize_bytes = (
            settings.max_file_size_mb * 1024 * 1024
            if settings.max_file_size_mb is not None
            else None
        )

        progress_callback = lambda percent, downloaded, total, speed: update_job_progress(
            session_factory,
            job.id,
            progress_percent=percent,
            downloaded_bytes=downloaded,
            total_bytes=total,
            speed_bps=speed,
        )

        update_job_progress(
            session_factory,
            job.id,
            progress_percent=0.0,
            downloaded_bytes=0,
            total_bytes=None,
            speed_bps=None,
            force=True,
        )

        result = _engine.download_job(
            source_type=source_type,
            url=job.url,
            job_type=job_type,
            requested_quality=job.requested_quality,
            target_dir=target_dir,
            cookie_file=cookie_file,
            max_filesize_bytes=max_filesize_bytes,
            progress_callback=progress_callback,
        )

        job.file_path = result.file_path
        job.thumbnail_path = result.thumbnail_path
        if result.filesize:
            job.downloaded_bytes = result.filesize
            job.total_bytes = result.filesize
        job.progress_percent = 100.0
        job.download_speed_bps = None
        job.last_progress_at = datetime.utcnow()
        if result.title and not job.final_title:
            job.final_title = result.title
        job.error_type = None
        job.error_message = None
        update_job_progress(
            session_factory,
            job.id,
            progress_percent=100.0,
            downloaded_bytes=job.downloaded_bytes,
            total_bytes=job.total_bytes,
            speed_bps=None,
            force=True,
        )
        maybe_archive_job_file(
            settings=settings,
            job_repo=repo,
            chat_settings_repo=chat_settings_repo,
            job=job,
        )
        mark_job_completed(
            session, job, metadata={"downloader": source_type.value.lower()}
        )

        if auth_profile:
            auth_repo.mark_success(auth_profile)
        log_with_context(
            logger,
            level=logging.INFO,
            message="Job download completed",
            stage="WORKER",
            job_id=job.id,
            file_path=result.file_path,
            downloader=source_type.value.lower(),
        )
    except DownloadError as exc:
        session.rollback()
        _handle_download_error(session, repo, job_id, exc)
    except asyncio.CancelledError:
        session.rollback()
        log_with_context(
            logger,
            level=logging.INFO,
            message="Job processing cancelled",
            stage="WORKER",
            job_id=job_id,
        )
        raise
    except Exception as exc:
        session.rollback()
        _handle_processing_error(session, repo, job_id, exc)
    finally:
        session.close()


def _handle_processing_error(
    session: Session, repo: JobRepository, job_id: int, exc: Exception
) -> None:
    try:
        job = repo.get_by_id(job_id)
        if job is None:
            log_with_context(
                logger,
                level=logging.ERROR,
                message="Job disappeared during processing error handling",
                stage="WORKER",
                job_id=job_id,
                error=str(exc),
            )
            return

        log_with_context(
            logger,
            level=logging.ERROR,
            message="Job processing failed",
            stage="WORKER",
            job_id=job.id,
            error=str(exc),
        )
        metadata = {"downloader": (job.source_type or "unknown").lower()}
        mark_job_failed(
            session,
            job,
            metadata=metadata,
            error_type=_classify_processing_exception(exc),
            error_message=str(exc),
        )
    except Exception:
        session.rollback()
        logger.exception("Failed to mark job as failed after processing error")


def _handle_download_error(
    session: Session, repo: JobRepository, job_id: int, exc: DownloadError
) -> None:
    try:
        job = repo.get_by_id(job_id)
        if job is None:
            log_with_context(
                logger,
                level=logging.ERROR,
                message="Job disappeared during download error handling",
                stage="WORKER",
                job_id=job_id,
                error=str(exc),
            )
            return

        log_with_context(
            logger,
            level=logging.ERROR,
            message="Job download failed",
            stage="WORKER",
            job_id=job.id,
            error_type=exc.error_type,
            http_status=getattr(exc, "http_status", None),
            error=str(exc),
        )
        error_type = exc.error_type or ErrorType.INTERNAL_ERROR
        if error_type == ErrorType.UNKNOWN:
            error_type = ErrorType.INTERNAL_ERROR
        mark_job_failed(
            session,
            job,
            metadata={"downloader": (job.source_type or "unknown").lower()},
            error_type=error_type,
            error_message=str(exc),
        )
    except Exception:
        session.rollback()
        logger.exception("Failed to mark job as failed after download error")
