"""Main entrypoint for the Telegram Media Archiver Bot."""
from config.settings import load_settings
from core.logging_utils import configure_logging, get_logger
from storage.db import get_engine, init_db


def main() -> None:
    """Initialize application configuration and logging."""

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
    engine = get_engine(settings)
    init_db(engine)
    logger.info("Database initialized at %s", settings.db_path)
    logger.info("Application initialized (Phase 2 – state machine ready)")


if __name__ == "__main__":
    main()
