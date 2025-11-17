"""Basic command handlers for the Telegram bot."""
from telegram import Update
from telegram.ext import ContextTypes

from core.logging_utils import get_logger

logger = get_logger(__name__)


async def ping_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reply with a simple 'pong' message and log the request."""

    user = update.effective_user
    chat = update.effective_chat

    logger.info(
        "Received /ping",
        extra={
            "stage": "BOT",
            "command": "ping",
            "user_id": user.id if user else None,
            "chat_id": chat.id if chat else None,
        },
    )

    if update.message:
        await update.message.reply_text("pong")


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Provide a friendly introduction to the bot."""

    user = update.effective_user
    chat = update.effective_chat

    logger.info(
        "Received /start",
        extra={
            "stage": "BOT",
            "command": "start",
            "user_id": user.id if user else None,
            "chat_id": chat.id if chat else None,
        },
    )

    message = (
        "Salam! I'm the Media Archiver bot. Send me media links and "
        "I'll queue them for download and delivery here as features roll out."
    )

    if update.message:
        await update.message.reply_text(message)
