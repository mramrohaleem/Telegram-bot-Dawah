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
        "I'll queue them for download and delivery here.\n\n"
        "Use /audio <url> or /video <url> to force the type, or set defaults "
        "with /set_type and /set_quality. Rename delivered jobs with "
        "/rename <job_id> <new title>."
    )

    if update.message:
        await update.message.reply_text(message)


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Provide usage instructions for the bot."""

    help_text = (
        "Send me any supported media link and I'll download it using your chat defaults.\n"
        "- /set_type <audio|video> to choose the default format\n"
        "- /set_quality <best|720p|480p|...> to pick preferred quality\n"
        "- /audio <url> or /video <url> to override defaults per message\n"
        "- /rename <job_id> <new title> to update the delivered title"
    )
    if update.message:
        await update.message.reply_text(help_text)
