"""Telegram application setup for the Media Archiver bot."""
from telegram.ext import Application, ApplicationBuilder, CommandHandler

from bot.handlers_basic import ping_handler, start_handler
from config.settings import Settings
from core.logging_utils import get_logger

logger = get_logger(__name__)


def build_application(settings: Settings) -> Application:
    """Create and configure the Telegram Application instance."""

    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN must be provided in settings")

    application = (
        ApplicationBuilder()
        .token(settings.telegram_bot_token)
        .build()
    )

    application.add_handler(CommandHandler("ping", ping_handler))
    application.add_handler(CommandHandler("start", start_handler))

    logger.info("Telegram application initialized with basic handlers")
    return application
