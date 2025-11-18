"""Database engine and session management utilities."""
from __future__ import annotations

import logging

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config.settings import Settings


class Base(DeclarativeBase):
    """Base class for all ORM models."""


def get_engine(settings: Settings) -> Engine:
    """Create a synchronous SQLite engine based on provided settings."""

    echo = bool(settings.debug_mode)
    return create_engine(
        f"sqlite:///{settings.db_path}",
        echo=echo,
        future=True,
    )


def get_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Return a configured session factory bound to the given engine."""

    return sessionmaker(bind=engine, class_=Session, autoflush=False)


def init_db(engine: Engine) -> None:
    """Create all tables in the database."""

    Base.metadata.create_all(bind=engine)
    _apply_lightweight_migrations(engine)


def _apply_lightweight_migrations(engine: Engine) -> None:
    """Ensure new columns exist when running against an existing SQLite DB."""

    logger = logging.getLogger(__name__)
    with engine.begin() as conn:
        result = conn.execute(text("PRAGMA table_info(jobs)"))
        columns = {row._mapping["name"] for row in result}

        migrations: dict[str, str] = {
            "progress_percent": "REAL",
            "downloaded_bytes": "INTEGER",
            "total_bytes": "INTEGER",
            "download_speed_bps": "REAL",
            "last_progress_at": "DATETIME",
            "thumbnail_path": "TEXT",
            "status_message_id": "TEXT",
            "status_chat_id": "TEXT",
        }

        for column_name, column_def in migrations.items():
            if column_name not in columns:
                logger.info("Applying lightweight migration to add column", extra={"column": column_name})
                conn.execute(
                    text(f"ALTER TABLE jobs ADD COLUMN {column_name} {column_def}")
                )
