"""Telegram handlers related to job creation from media links."""
from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from core.job_service import JobCreationError, JobService
from core.logging_utils import get_logger

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

    job_service = _get_job_service(context)

    try:
        job = job_service.create_job_from_message(
            chat_id=chat.id if chat else None,
            user_id=user.id if user else None,
            text=message.text,
        )
    except JobCreationError as exc:
        logger.info(
            "Failed to create job from message",
            extra={
                "stage": "BOT",
                "reason": str(exc),
                "chat_id": chat.id if chat else None,
                "user_id": user.id if user else None,
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
