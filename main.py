"""Main entrypoint for the Telegram Media Archiver Bot."""
import asyncio
import contextlib

from bot.app import build_application
from bot.delivery import delivery_loop
from config.settings import load_settings
from core.cleanup import cleanup_loop
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
    worker_task: asyncio.Task | None = None
    delivery_task: asyncio.Task | None = None
    cleanup_task: asyncio.Task | None = None

    try:
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        logger.info("Application started, entering idle state")

        worker_task = asyncio.create_task(worker_loop(settings, session_factory))
        delivery_task = asyncio.create_task(
            delivery_loop(settings, session_factory, application)
        )
        if settings.tmp_retention_days and settings.tmp_retention_days > 0:
            cleanup_task = asyncio.create_task(
                cleanup_loop(settings, session_factory=session_factory)
            )

        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            logger.info("Main loop cancelled, shutting down")
    finally:
        for task in (worker_task, delivery_task, cleanup_task):
            if task:
                task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            if worker_task:
                await worker_task
            if delivery_task:
                await delivery_task
            if cleanup_task:
                await cleanup_task
        if application.updater:
            await application.updater.stop()
        await application.stop()
        await application.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
