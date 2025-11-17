"""Admin and diagnostic command handlers."""
from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from bot.delivery import send_job_media
from core.logging_utils import get_logger
from storage.models import JobStatus
from storage.repositories import JobRepository

logger = get_logger(__name__)


def _get_session_factory(context: ContextTypes.DEFAULT_TYPE):
    session_factory = context.application.bot_data.get("session_factory")
    if session_factory is None:
        raise RuntimeError("Session factory not configured for bot")
    return session_factory


async def job_info_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle `/job <id>` to fetch job details and resend the media if ready."""

    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if message is None or chat is None:
        return

    logger.info(
        "Received /job command",
        extra={
            "stage": "BOT",
            "command": "job",
            "chat_id": chat.id,
            "user_id": user.id if user else None,
            "args": context.args,
        },
    )

    if not context.args:
        await message.reply_text("Usage: /job <id>")
        return

    try:
        job_id = int(context.args[0])
    except ValueError:
        await message.reply_text("Please provide a valid numeric job id.")
        return

    session_factory = _get_session_factory(context)
    session = session_factory()
    try:
        repo = JobRepository(session)
        job = repo.get_by_id(job_id)
        if job is None:
            await message.reply_text(f"Job #{job_id} not found.")
            return

        if job.chat_id and str(job.chat_id) != str(chat.id):
            await message.reply_text("This job belongs to a different chat.")
            return

        status_text = (
            f"Job #{job.id}: status={job.status} source={job.source_type} "
            f"type={job.job_type}"
        )
        if job.error_message:
            status_text += f"\nLast error: {job.error_message}"
        if job.delivery_last_error:
            status_text += f"\nDelivery error: {job.delivery_last_error}"

        await message.reply_text(status_text)

        if job.status != JobStatus.COMPLETED.value:
            return
        if not job.file_path:
            await message.reply_text("Job is completed but file path is missing.")
            return

        try:
            sent_message = await send_job_media(context.application, job)
            repo.mark_job_delivered(job, telegram_message_id=sent_message.message_id)
            await message.reply_text("Job file sent above.")
        except Exception as exc:  # pragma: no cover - defensive
            repo.mark_delivery_failure(job, error_message=str(exc))
            await message.reply_text(f"Failed to send job file: {exc}")
    finally:
        session.close()
