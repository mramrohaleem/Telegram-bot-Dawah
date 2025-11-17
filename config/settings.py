"""Settings management for environment-driven configuration."""
import os
from dataclasses import dataclass
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


def _get_bool(value: Optional[str], default: bool = False) -> bool:
    """Convert common truthy/falsy strings to boolean values."""

    if value is None:
        return default
    normalized = value.strip().lower()
    return normalized in {"1", "true", "yes", "on"}


def load_settings() -> Settings:
    """Load settings from environment variables with validation."""

    required_keys = [
        "DB_PATH",
        "TMP_ROOT",
        "ARCHIVE_ROOT",
        "AUTH_PROFILE_DIR",
        "TELEGRAM_BOT_TOKEN",
    ]

    missing = [key for key in required_keys if not os.environ.get(key)]
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}"
        )

    return Settings(
        db_path=os.environ["DB_PATH"],
        tmp_root=os.environ["TMP_ROOT"],
        archive_root=os.environ["ARCHIVE_ROOT"],
        auth_profile_dir=os.environ["AUTH_PROFILE_DIR"],
        telegram_bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
        environment=os.environ.get("ENVIRONMENT", "dev"),
        mock_downloads=_get_bool(os.environ.get("MOCK_DOWNLOADS"), False),
        debug_mode=_get_bool(os.environ.get("DEBUG_MODE"), False),
        maintenance_mode=_get_bool(os.environ.get("MAINTENANCE_MODE"), False),
    )
