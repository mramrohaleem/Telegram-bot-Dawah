"""Telegram application setup for the Media Archiver bot."""
from sqlalchemy.orm import Session, sessionmaker
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from bot.handlers_admin import job_info_handler
from bot.handlers_basic import help_handler, ping_handler, start_handler
from bot.handlers_jobs import (
    handle_media_link,
    rename_job_handler,
    selection_callback_handler,
    settings_callback_handler,
    settings_handler,
    status_handler,
)
from config.settings import Settings
from core.job_service import JobService
from core.logging_utils import get_logger

logger = get_logger(__name__)


def build_application(
    settings: Settings, *, session_factory: sessionmaker[Session]
) -> Application:
    """Create and configure the Telegram Application instance."""

    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN must be provided in settings")
    job_service = JobService(session_factory)

    application = ApplicationBuilder().token(settings.telegram_bot_token).build()
    application.bot_data["job_service"] = job_service
    application.bot_data["session_factory"] = session_factory

    application.add_handler(CommandHandler("ping", ping_handler))
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("help", help_handler))
    application.add_handler(CommandHandler("job", job_info_handler))
    application.add_handler(CommandHandler("status", status_handler))
    application.add_handler(CommandHandler("settings", settings_handler))
    application.add_handler(CommandHandler("rename", rename_job_handler))
    application.add_handler(
        MessageHandler(
            filters.TEXT & (filters.Entity("url") | filters.Entity("text_link")),
            handle_media_link,
        )
    )
    application.add_handler(CallbackQueryHandler(status_handler, pattern=r"^status$"))
    application.add_handler(
        CallbackQueryHandler(selection_callback_handler, pattern=r"^(sel|default)")
    )
    application.add_handler(CallbackQueryHandler(settings_callback_handler, pattern=r"^settings"))

    logger.info("Telegram application initialized with job handlers")
    return application
