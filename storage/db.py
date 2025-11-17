"""Database engine and session management utilities."""
from __future__ import annotations

from sqlalchemy import create_engine
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
