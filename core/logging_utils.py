"""Central logging configuration utilities."""
import logging
import sys
from typing import Mapping

from config.settings import Settings


def configure_logging(settings: Settings) -> None:
    """Configure root logging with stdout handler and structured format."""

    log_level = logging.DEBUG if settings.debug_mode else logging.INFO
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Clear existing handlers to avoid duplicate logs on reconfiguration.
    root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt=(
            "%(asctime)s level=%(levelname)s logger=%(name)s "
            "message=%(message)s"
        ),
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Return a logger configured with the global logging settings."""

    return logging.getLogger(name)


def _serialize_context(context: Mapping[str, object]) -> str:
    return " ".join(f"{key}={value}" for key, value in context.items() if value is not None)


def log_with_context(
    logger: logging.Logger, level: int, message: str, **context: object
) -> None:
    """Log a message with structured key/value context appended."""

    context_str = _serialize_context(context)
    if context_str:
        logger.log(level, f"{message} {context_str}")
    else:
        logger.log(level, message)
