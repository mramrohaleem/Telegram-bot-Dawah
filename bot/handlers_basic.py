"""Basic command handlers for the Telegram bot."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from core.logging_utils import get_logger
from bot import texts

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
        await update.message.reply_text(texts.PING_RESPONSE_AR)


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

    if update.message:
        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton(texts.STATUS_BUTTON_AR, callback_data="status")],
                [InlineKeyboardButton("⚙️ الإعدادات", callback_data="settings")],
            ]
        )
        await update.message.reply_text(texts.START_MESSAGE_AR, reply_markup=keyboard)


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Provide usage instructions for the bot."""
    if update.message:
        await update.message.reply_text(texts.HELP_MESSAGE_AR)
