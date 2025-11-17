"""Delivery loop for sending completed jobs back to Telegram chats."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from telegram import InputFile, Message
from telegram.ext import Application

from config.settings import Settings
from core.logging_utils import get_logger, log_with_context
from core.filename_utils import sanitize_title_to_filename
from storage.models import ErrorType, Job, JobType
from storage.repositories import JobRepository

logger = get_logger(__name__)


async def delivery_loop(
    settings: Settings, session_factory, application: Application
) -> None:
    """Background loop that periodically sends completed jobs to Telegram."""

    poll_interval = settings.delivery_poll_interval_seconds
    max_attempts = settings.max_delivery_attempts

    log_with_context(
        logger,
        level=logging.INFO,
        message="Starting delivery loop",
        stage="DELIVERY",
        poll_interval=poll_interval,
        max_attempts=max_attempts,
    )

    try:
        while True:
            try:
                await _deliver_once(session_factory, application, max_attempts)
            except Exception as exc:  # pragma: no cover - defensive
                log_with_context(
                    logger,
                    level=logging.ERROR,
                    message="Delivery loop iteration failed",
                    stage="DELIVERY",
                    error=str(exc),
                )
            await asyncio.sleep(poll_interval)
    except asyncio.CancelledError:
        log_with_context(
            logger,
            level=logging.INFO,
            message="Delivery loop cancelled",
            stage="DELIVERY",
        )
        raise


async def _deliver_once(
    session_factory, application: Application, max_attempts: int
) -> None:
    session = session_factory()
    try:
        repo = JobRepository(session)
        jobs = repo.list_completed_undelivered_jobs(limit=50)
        for job in jobs:
            if job.delivery_attempts is not None and job.delivery_attempts >= max_attempts:
                log_with_context(
                    logger,
                    level=logging.INFO,
                    message="Skipping delivery due to max attempts",
                    stage="DELIVERY",
                    job_id=job.id,
                    chat_id=job.chat_id,
                )
                continue

            if job.chat_id is None:
                repo.mark_delivery_failure(job, error_message="Missing chat_id for delivery")
                continue

            if not job.file_path or not os.path.exists(job.file_path):
                repo.mark_delivery_failure(job, error_message="File missing for delivery")
                log_with_context(
                    logger,
                    level=logging.WARNING,
                    message="Cannot deliver job because file is missing",
                    stage="DELIVERY",
                    job_id=job.id,
                    chat_id=job.chat_id,
                )
                continue

            try:
                message = await _send_job_media(application, job)
            except Exception as exc:  # pragma: no cover - defensive
                repo.mark_delivery_failure(job, error_message=str(exc))
                log_with_context(
                    logger,
                    level=logging.ERROR,
                    message="Failed to deliver job",
                    stage="DELIVERY",
                    job_id=job.id,
                    chat_id=job.chat_id,
                    error=str(exc),
                )
                continue

            repo.mark_job_delivered(job, telegram_message_id=message.message_id)
            log_with_context(
                logger,
                level=logging.INFO,
                message="Delivered job to Telegram",
                stage="DELIVERY",
                job_id=job.id,
                chat_id=job.chat_id,
                message_id=message.message_id,
            )
        await _notify_failures(repo, application, max_attempts)
    finally:
        session.close()


async def _send_job_media(application: Application, job: Job) -> Message:
    try:
        job_type = JobType(job.job_type) if job.job_type else JobType.VIDEO
    except ValueError:
        job_type = JobType.VIDEO
    chosen_title = job.final_title or os.path.basename(job.file_path or "") or "Media"
    file_ext = Path(job.file_path or "").suffix.lstrip(".")
    if not file_ext:
        file_ext = "mp3" if job_type == JobType.AUDIO else "mp4"
    filename = sanitize_title_to_filename(chosen_title, file_ext)

    log_with_context(
        logger,
        level=logging.INFO,
        message="Preparing media for delivery",
        stage="DELIVERY",
        job_id=job.id,
        has_custom_title=bool(job.final_title),
        filename=filename,
    )

    with open(job.file_path, "rb") as fp:  # type: ignore[arg-type]
        input_file = InputFile(fp, filename=filename)
        if job_type == JobType.AUDIO:
            return await application.bot.send_audio(
                chat_id=job.chat_id,
                audio=input_file,
                caption=chosen_title,
            )
        if job_type == JobType.VIDEO:
            return await application.bot.send_video(
                chat_id=job.chat_id,
                video=input_file,
                caption=chosen_title,
            )
        return await application.bot.send_document(
            chat_id=job.chat_id,
            document=input_file,
            caption=chosen_title,
        )


async def send_job_media(application: Application, job: Job) -> Message:
    """Public helper to send a job's media to Telegram."""

    return await _send_job_media(application, job)


async def _notify_failures(
    repo: JobRepository, application: Application, max_attempts: int
) -> None:
    failed_jobs = repo.list_failed_unnotified_jobs(limit=20)
    delivery_failures = repo.list_delivery_failures_needing_notice(
        max_attempts=max_attempts, limit=20
    )

    for job in failed_jobs:
        message = _build_failure_message(job, is_delivery_failure=False)
        await _send_failure_notice(application, repo, job, message)

    for job in delivery_failures:
        message = _build_failure_message(job, is_delivery_failure=True)
        await _send_failure_notice(application, repo, job, message)


def _build_failure_message(job: Job, *, is_delivery_failure: bool) -> str:
    if is_delivery_failure:
        reason = job.delivery_last_error or "Delivery failed after multiple attempts."
        return f"Delivery failed for job #{job.id}: {reason}"

    try:
        error_type = ErrorType(job.error_type) if job.error_type else None
    except ValueError:
        error_type = None

    if error_type == ErrorType.SIZE_LIMIT:
        return "Downloading this media failed: file is too large for the configured limit."
    if error_type == ErrorType.GEO_BLOCK:
        return "Downloading this media failed because it is blocked in this region."
    if error_type == ErrorType.AUTH_ERROR:
        return "Downloading this media failed: the site requires login or valid cookies."
    if error_type == ErrorType.UNSUPPORTED_SOURCE:
        return "Downloading this media failed: the source is not supported."
    return (
        f"Downloading this media failed (type: {job.error_type or 'unknown'}). "
        "Ask an admin with /job <id> if you need more details."
    )


async def _send_failure_notice(
    application: Application, repo: JobRepository, job: Job, message: str
) -> None:
    if job.chat_id is None:
        return
    try:
        await application.bot.send_message(chat_id=job.chat_id, text=message)
        log_with_context(
            logger,
            level=logging.INFO,
            message="User notified of failure",
            stage="FAIL_NOTIFY",
            job_id=job.id,
            chat_id=job.chat_id,
            error_type=job.error_type,
            delivery_error=job.delivery_last_error,
        )
    except Exception as exc:  # pragma: no cover - defensive
        log_with_context(
            logger,
            level=logging.WARNING,
            message="Failed to send failure notification",
            stage="FAIL_NOTIFY",
            job_id=job.id,
            chat_id=job.chat_id,
            error=str(exc),
        )
    finally:
        if job.failure_notified_at is None:
            repo.mark_failure_notified(job)
