"""Delivery loop for sending completed jobs back to Telegram chats."""
from __future__ import annotations

import asyncio
import os

from telegram import InputFile, Message
from telegram.ext import Application

from config.settings import Settings
from core.logging_utils import get_logger, log_with_context
from storage.models import Job, JobType
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
    finally:
        session.close()


async def _send_job_media(application: Application, job: Job) -> Message:
    try:
        job_type = JobType(job.job_type) if job.job_type else JobType.VIDEO
    except ValueError:
        job_type = JobType.VIDEO
    caption = job.final_title or os.path.basename(job.file_path or "") or "Media"
    filename = os.path.basename(job.file_path or "output")

    with open(job.file_path, "rb") as fp:  # type: ignore[arg-type]
        input_file = InputFile(fp, filename=filename)
        if job_type == JobType.AUDIO:
            return await application.bot.send_audio(
                chat_id=job.chat_id,
                audio=input_file,
                caption=caption,
            )
        if job_type == JobType.VIDEO:
            return await application.bot.send_video(
                chat_id=job.chat_id,
                video=input_file,
                caption=caption,
            )
        return await application.bot.send_document(
            chat_id=job.chat_id,
            document=input_file,
            caption=caption,
        )


async def send_job_media(application: Application, job: Job) -> Message:
    """Public helper to send a job's media to Telegram."""

    return await _send_job_media(application, job)
