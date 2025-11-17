"""Telegram application setup for the Media Archiver bot."""
from telegram.ext import Application, ApplicationBuilder, CommandHandler, MessageHandler, filters

from bot.handlers_basic import ping_handler, start_handler
from bot.handlers_jobs import handle_media_link
from config.settings import Settings
from core.job_service import JobService
from core.logging_utils import get_logger
from storage.db import get_engine, get_session_factory, init_db

logger = get_logger(__name__)


def build_application(settings: Settings) -> Application:
    """Create and configure the Telegram Application instance."""

    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN must be provided in settings")

    engine = get_engine(settings)
    init_db(engine)
    session_factory = get_session_factory(engine)
    job_service = JobService(session_factory)

    application = ApplicationBuilder().token(settings.telegram_bot_token).build()
    application.bot_data["job_service"] = job_service

    application.add_handler(CommandHandler("ping", ping_handler))
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(
        MessageHandler(
            filters.TEXT & (filters.Entity("url") | filters.Entity("text_link")),
            handle_media_link,
        )
    )

    logger.info("Telegram application initialized with job handlers")
    return application
