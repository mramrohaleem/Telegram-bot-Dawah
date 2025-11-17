"""Main entrypoint for the Telegram Media Archiver Bot."""
import asyncio
import contextlib

from bot.app import build_application
from config.settings import load_settings
from core.logging_utils import configure_logging, get_logger
from core.worker import worker_loop
from storage.db import get_engine, get_session_factory, init_db


async def main() -> None:
    """Initialize application configuration, logging, and start the bot."""

    settings = load_settings()
    configure_logging(settings)
    logger = get_logger(__name__)

    logger.info(
        "Settings loaded environment=%s debug_mode=%s maintenance_mode=%s "
        "mock_downloads=%s tmp_root=%s archive_root=%s auth_profile_dir=%s db_path=%s",
        settings.environment,
        settings.debug_mode,
        settings.maintenance_mode,
        settings.mock_downloads,
        settings.tmp_root,
        settings.archive_root,
        settings.auth_profile_dir,
        settings.db_path,
    )
    logger.info("Starting Telegram bot (Phase 4 – job creation from messages)")
    engine = get_engine(settings)
    init_db(engine)
    session_factory = get_session_factory(engine)

    application = build_application(settings, session_factory=session_factory)
    worker_task = asyncio.create_task(worker_loop(settings, session_factory))

    logger.info("Starting Telegram bot and worker loop")

    try:
        await application.run_polling()
    finally:
        worker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker_task


if __name__ == "__main__":
    asyncio.run(main())
