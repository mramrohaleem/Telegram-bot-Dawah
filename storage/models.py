from __future__ import annotations

"""ORM models and domain enums for the storage layer."""

from datetime import datetime
from enum import StrEnum
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from storage.db import Base


class JobStatus(StrEnum):
    """Lifecycle status for a job."""

    PENDING = "PENDING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class JobType(StrEnum):
    """Type of media requested for a job."""

    VIDEO = "VIDEO"
    AUDIO = "AUDIO"


class SourceType(StrEnum):
    """Supported content sources."""

    YOUTUBE = "YOUTUBE"
    FACEBOOK = "FACEBOOK"
    ARCHIVE = "ARCHIVE"
    TARIQ_ALLAH = "TARIQ_ALLAH"
    GENERIC = "GENERIC"


class ErrorType(StrEnum):
    """Error classification for failed jobs."""

    NETWORK_ERROR = "NETWORK_ERROR"
    HTTP_ERROR = "HTTP_ERROR"
    AUTH_ERROR = "AUTH_ERROR"
    RATE_LIMIT = "RATE_LIMIT"
    EXTRACTOR_ERROR = "EXTRACTOR_ERROR"
    EXTRACTOR_UPDATE_REQUIRED = "EXTRACTOR_UPDATE_REQUIRED"
    GEO_BLOCK = "GEO_BLOCK"
    SIZE_LIMIT = "SIZE_LIMIT"
    FORMAT_NOT_FOUND = "FORMAT_NOT_FOUND"
    PARSER_ERROR = "PARSER_ERROR"
    PROTECTED_CONTENT = "PROTECTED_CONTENT"
    UNSUPPORTED_SOURCE = "UNSUPPORTED_SOURCE"
    UNKNOWN = "UNKNOWN"


class AuthProfileStatus(StrEnum):
    """Status of an authentication profile."""

    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    DISABLED = "DISABLED"


class Job(Base):
    """Represents a single download/conversion request."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String, nullable=False)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    job_type: Mapped[str] = mapped_column(String, nullable=False)
    requested_quality: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default=JobStatus.PENDING.value, index=True
    )
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    job_key: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    auth_profile_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("auth_profiles.id"), nullable=True
    )
    user_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    chat_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    final_title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    telegram_message_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    delivery_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    delivery_last_error: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    events: Mapped[list["JobEvent"]] = relationship(
        "JobEvent", back_populates="job", cascade="all, delete-orphan"
    )
    auth_profile: Mapped[Optional["AuthProfile"]] = relationship("AuthProfile")


class JobEvent(Base):
    """Timeline entries recording what happened to a job."""

    __tablename__ = "job_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("jobs.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    job: Mapped[Job] = relationship("Job", back_populates="events")


class AuthProfile(Base):
    """Authentication context for downloaders."""

    __tablename__ = "auth_profiles"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    cookie_file_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default=AuthProfileStatus.ACTIVE.value
    )
    failure_count_recent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_success_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_failure_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    jobs: Mapped[list[Job]] = relationship("Job", back_populates="auth_profile")


class ChatSettings(Base):
    """Per-chat configuration and defaults."""

    __tablename__ = "chat_settings"

    chat_id: Mapped[str] = mapped_column(String, primary_key=True)
    archive_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    default_job_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    default_quality: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
