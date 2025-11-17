"""Settings management for environment-driven configuration."""
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class Settings:
    """Runtime configuration loaded from environment variables."""

    db_path: str
    tmp_root: str
    archive_root: str
    auth_profile_dir: str
    telegram_bot_token: str
    environment: str = "dev"
    mock_downloads: bool = False
    debug_mode: bool = False
    maintenance_mode: bool = False
    max_parallel_jobs: int = 3
    max_queue_length: int = 100
    worker_poll_interval_seconds: int = 5
    delivery_poll_interval_seconds: int = 5
    max_delivery_attempts: int = 5
    max_file_size_mb: Optional[int] = None
    tmp_retention_days: Optional[int] = None
    cleanup_poll_interval_seconds: int = 3600


def _get_bool(value: Optional[str], default: bool = False) -> bool:
    """Convert common truthy/falsy strings to boolean values."""

    if value is None:
        return default
    normalized = value.strip().lower()
    return normalized in {"1", "true", "yes", "on"}


def _get_int(value: Optional[str], default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _get_optional_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def load_settings() -> Settings:
    """Load settings from environment variables with validation."""

    base_dir = Path(os.getenv("APP_BASE_DIR", Path.cwd()))

    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not telegram_bot_token:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN")

    db_path = Path(os.getenv("DB_PATH", base_dir / "db.sqlite3"))
    tmp_root = Path(os.getenv("TMP_ROOT", base_dir / "tmp"))
    archive_root = Path(os.getenv("ARCHIVE_ROOT", base_dir / "archive"))
    auth_dir = Path(os.getenv("AUTH_PROFILE_DIR", base_dir / "auth_profiles"))

    tmp_root.mkdir(parents=True, exist_ok=True)
    archive_root.mkdir(parents=True, exist_ok=True)
    auth_dir.mkdir(parents=True, exist_ok=True)

    return Settings(
        db_path=str(db_path),
        tmp_root=str(tmp_root),
        archive_root=str(archive_root),
        auth_profile_dir=str(auth_dir),
        telegram_bot_token=telegram_bot_token,
        environment=os.environ.get("ENVIRONMENT", "dev"),
        mock_downloads=_get_bool(os.environ.get("MOCK_DOWNLOADS"), False),
        debug_mode=_get_bool(os.environ.get("DEBUG_MODE"), False),
        maintenance_mode=_get_bool(os.environ.get("MAINTENANCE_MODE"), False),
        max_parallel_jobs=_get_int(os.environ.get("MAX_PARALLEL_JOBS"), 3),
        max_queue_length=_get_int(os.environ.get("MAX_QUEUE_LENGTH"), 100),
        worker_poll_interval_seconds=_get_int(
            os.environ.get("WORKER_POLL_INTERVAL_SECONDS"), 5
        ),
        delivery_poll_interval_seconds=_get_int(
            os.environ.get("DELIVERY_POLL_INTERVAL_SECONDS"), 5
        ),
        max_delivery_attempts=_get_int(
            os.environ.get("MAX_DELIVERY_ATTEMPTS"), 5
        ),
        max_file_size_mb=_get_optional_int(os.environ.get("MAX_FILE_SIZE_MB")),
        tmp_retention_days=_get_optional_int(os.environ.get("TMP_RETENTION_DAYS")),
        cleanup_poll_interval_seconds=_get_int(
            os.environ.get("CLEANUP_POLL_INTERVAL_SECONDS"), 3600
        ),
    )
