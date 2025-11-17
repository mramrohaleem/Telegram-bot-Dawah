"""Telegram handlers related to job creation from media links."""
from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from core.job_service import JobCreationError, JobService
from core.logging_utils import get_logger, log_with_context
from storage.models import JobType
from storage.repositories import ChatSettingsRepository, JobRepository

logger = get_logger(__name__)


def _get_job_service(context: ContextTypes.DEFAULT_TYPE) -> JobService:
    job_service = context.application.bot_data.get("job_service")
    if job_service is None:
        raise RuntimeError("JobService is not configured in bot_data")
    return job_service


async def handle_media_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle messages containing URLs and create jobs."""

    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not message or not message.text:
        return

    await _create_job_from_text(
        update,
        context,
        text=message.text,
        forced_job_type=None,
    )


async def audio_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message or not message.text:
        return
    remainder = message.text.partition(" ")[2]
    await _create_job_from_text(
        update, context, text=remainder, forced_job_type=JobType.AUDIO
    )


async def video_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message or not message.text:
        return
    remainder = message.text.partition(" ")[2]
    await _create_job_from_text(
        update, context, text=remainder, forced_job_type=JobType.VIDEO
    )


async def set_type_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not message or not chat:
        return

    if not context.args:
        await message.reply_text("Usage: /set_type <audio|video>")
        return

    value = context.args[0].strip().lower()
    if value not in {"audio", "video"}:
        await message.reply_text("Type must be 'audio' or 'video'.")
        return

    job_type = JobType.AUDIO if value == "audio" else JobType.VIDEO
    session_factory = context.application.bot_data.get("session_factory")
    if session_factory is None:
        raise RuntimeError("Session factory missing in bot_data")
    session = session_factory()
    try:
        settings_repo = ChatSettingsRepository(session)
        existing = settings_repo.get_or_create(chat.id)
        settings_repo.update_defaults(
            chat.id,
            default_job_type=job_type,
            default_quality=existing.default_quality,
            interactive_hints_enabled=existing.interactive_hints_enabled,
        )
        log_with_context(
            logger,
            level=logging.INFO,
            message="Updated default job type",
            stage="USER_CMD",
            chat_id=chat.id,
            user_id=user.id if user else None,
            default_job_type=job_type.value,
        )
    finally:
        session.close()

    await message.reply_text(
        f"Default job type set to {job_type.value.lower()} for this chat."
    )


async def set_quality_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not message or not chat:
        return

    if not context.args:
        await message.reply_text("Usage: /set_quality <best|720p|480p|360p|...>")
        return

    quality = " ".join(context.args).strip()
    session_factory = context.application.bot_data.get("session_factory")
    if session_factory is None:
        raise RuntimeError("Session factory missing in bot_data")
    session = session_factory()
    try:
        settings_repo = ChatSettingsRepository(session)
        existing = settings_repo.get_or_create(chat.id)
        settings_repo.update_defaults(
            chat.id,
            default_job_type=existing.default_job_type,
            default_quality=quality,
            interactive_hints_enabled=existing.interactive_hints_enabled,
        )
        log_with_context(
            logger,
            level=logging.INFO,
            message="Updated default quality",
            stage="USER_CMD",
            chat_id=chat.id,
            user_id=user.id if user else None,
            default_quality=quality,
        )
    finally:
        session.close()

    await message.reply_text(f"Default quality set to '{quality}'.")


async def rename_job_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not message or not chat:
        return

    if len(context.args) < 2:
        await message.reply_text("Usage: /rename <job_id> <new title>")
        return

    try:
        job_id = int(context.args[0])
    except ValueError:
        await message.reply_text("Job id must be a number.")
        return

    new_title = " ".join(context.args[1:]).strip()
    if not new_title:
        await message.reply_text("Please provide a new title after the job id.")
        return

    session_factory = context.application.bot_data.get("session_factory")
    if session_factory is None:
        raise RuntimeError("Session factory missing in bot_data")
    session = session_factory()
    try:
        repo = JobRepository(session)
        job = repo.get_by_id(job_id)
        if job is None:
            await message.reply_text("Job not found.")
            return
        if str(job.chat_id) != str(chat.id):
            await message.reply_text("You can only rename jobs from this chat.")
            return

        job.final_title = new_title
        repo.save(job)
        log_with_context(
            logger,
            level=logging.INFO,
            message="Job renamed",
            stage="USER_CMD",
            job_id=job.id,
            chat_id=chat.id,
            user_id=user.id if user else None,
        )
    finally:
        session.close()

    await message.reply_text(f'Renamed job {job_id} to: "{new_title}"')


async def _create_job_from_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    text: str,
    forced_job_type: JobType | None,
) -> None:
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not message:
        return

    if not text or not text.strip():
        await message.reply_text("Please provide a URL after the command.")
        return

    job_service = _get_job_service(context)

    try:
        job = job_service.create_job_from_message(
            chat_id=chat.id if chat else None,
            user_id=user.id if user else None,
            text=text,
            forced_job_type=forced_job_type,
            forced_quality=None,
        )
    except JobCreationError as exc:
        logger.info(
            "Failed to create job from message",
            extra={
                "stage": "BOT",
                "reason": str(exc),
                "chat_id": chat.id if chat else None,
                "user_id": user.id if user else None,
                "forced_job_type": forced_job_type.value if forced_job_type else None,
            },
        )
        await message.reply_text(
            "I couldn't create a job from that message. Please send a valid media link."
        )
        return

    logger.info(
        "Created job from message",
        extra={
            "stage": "BOT",
            "job_id": job.id,
            "chat_id": chat.id if chat else None,
            "user_id": user.id if user else None,
            "source_type": job.source_type,
            "job_type": job.job_type,
        },
    )

    await message.reply_text(
        f"Your request has been registered as job #{job.id}. "
        "Processing will start soon in the background."
    )
