"""Repository helpers for database operations."""
from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Mapping, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from storage.models import (
    AuthProfile,
    AuthProfileStatus,
    ChatSettings,
    ErrorType,
    Job,
    JobEvent,
    JobStatus,
    JobType,
    SourceType,
)


def _enum_value(value: str | Enum | None) -> Optional[str]:
    """Return the string value for enum members while allowing raw strings."""

    if value is None:
        return None
    return value.value if isinstance(value, Enum) else value


class JobRepository:
    """CRUD operations for Job entities."""

    def __init__(self, session: Session):
        self.session = session

    def create_job(
        self,
        *,
        url: str,
        source_type: SourceType | str,
        job_type: JobType | str,
        requested_quality: Optional[str],
        job_key: str,
        user_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        auth_profile_id: Optional[str] = None,
        commit: bool = True,
    ) -> Job:
        job = Job(
            url=url,
            source_type=_enum_value(source_type),
            job_type=_enum_value(job_type),
            requested_quality=requested_quality,
            status=JobStatus.PENDING.value,
            retry_count=0,
            job_key=job_key,
            auth_profile_id=auth_profile_id,
            user_id=user_id,
            chat_id=chat_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        self.session.add(job)
        if commit:
            self.session.commit()
            self.session.refresh(job)
        else:
            self.session.flush()
        return job

    def get_by_id(self, job_id: int) -> Optional[Job]:
        return self.session.get(Job, job_id)

    def get_by_job_key(self, job_key: str) -> Optional[Job]:
        stmt = select(Job).where(Job.job_key == job_key)
        return self.session.execute(stmt).scalar_one_or_none()

    def list_by_status(self, status: JobStatus | str, limit: int = 100) -> list[Job]:
        stmt = (
            select(Job)
            .where(Job.status == _enum_value(status))
            .order_by(Job.created_at.asc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars().all())

    def list_jobs_by_status(
        self, status: JobStatus | str, limit: int = 100
    ) -> Sequence[Job]:
        stmt = (
            select(Job)
            .where(Job.status == _enum_value(status))
            .order_by(Job.created_at.asc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars().all())

    def list_cleanup_candidates(
        self, *, cutoff: datetime, limit: int = 50
    ) -> Sequence[Job]:
        stmt = (
            select(Job)
            .where(
                Job.status.in_([JobStatus.COMPLETED.value, JobStatus.FAILED.value]),
                Job.is_archived.is_(False),
                Job.file_path.is_not(None),
                Job.updated_at < cutoff,
            )
            .order_by(Job.updated_at.asc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars().all())

    def count_jobs_by_status(self, status: JobStatus | str) -> int:
        stmt = select(func.count()).select_from(Job).where(Job.status == _enum_value(status))
        return int(self.session.execute(stmt).scalar_one())

    def save(self, job: Job) -> None:
        job.updated_at = datetime.utcnow()
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)

    def list_completed_undelivered_jobs(self, limit: int = 50) -> Sequence[Job]:
        """Return completed jobs that have not been delivered to Telegram."""

        stmt = (
            select(Job)
            .where(
                Job.status == JobStatus.COMPLETED.value,
                Job.delivered_at.is_(None),
                Job.chat_id.is_not(None),
            )
            .order_by(Job.created_at.asc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars().all())

    def list_failed_unnotified_jobs(self, limit: int = 20) -> Sequence[Job]:
        stmt = (
            select(Job)
            .where(
                Job.status == JobStatus.FAILED.value,
                Job.chat_id.is_not(None),
                Job.failure_notified_at.is_(None),
            )
            .order_by(Job.updated_at.asc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars().all())

    def list_delivery_failures_needing_notice(
        self, max_attempts: int, limit: int = 20
    ) -> Sequence[Job]:
        stmt = (
            select(Job)
            .where(
                Job.status == JobStatus.COMPLETED.value,
                Job.delivered_at.is_(None),
                Job.delivery_attempts >= max_attempts,
                Job.chat_id.is_not(None),
                Job.failure_notified_at.is_(None),
            )
            .order_by(Job.updated_at.asc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars().all())

    def mark_job_delivered(
        self, job: Job, *, telegram_message_id: str | int
    ) -> None:
        job.delivery_attempts = (job.delivery_attempts or 0) + 1
        job.delivered_at = datetime.utcnow()
        job.telegram_message_id = str(telegram_message_id)
        job.delivery_last_error = None
        job.updated_at = datetime.utcnow()
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)

    def mark_delivery_failure(self, job: Job, *, error_message: str) -> None:
        job.delivery_attempts = (job.delivery_attempts or 0) + 1
        job.delivery_last_error = error_message[:255]
        job.updated_at = datetime.utcnow()
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)

    def mark_failure_notified(self, job: Job) -> None:
        job.failure_notified_at = datetime.utcnow()
        job.updated_at = datetime.utcnow()
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)


class JobEventRepository:
    """Repository for recording job timeline events."""

    def __init__(self, session: Session):
        self.session = session

    def add_event(
        self,
        job_id: int,
        event_type: str,
        data: Optional[dict] = None,
        *,
        commit: bool = True,
    ) -> JobEvent:
        event = JobEvent(
            job_id=job_id,
            event_type=event_type,
            data=data,
            created_at=datetime.utcnow(),
        )
        self.session.add(event)
        if commit:
            self.session.commit()
            self.session.refresh(event)
        else:
            self.session.flush()
        return event

    def add_status_change_event(
        self,
        *,
        job_id: int,
        old_status: JobStatus | str,
        new_status: JobStatus | str,
        metadata: Optional[Mapping[str, object]] = None,
        error_type: ErrorType | str | None = None,
        error_message: str | None = None,
        commit: bool = True,
    ) -> JobEvent:
        data: dict[str, object] = {
            "from": _enum_value(old_status) or str(old_status),
            "to": _enum_value(new_status) or str(new_status),
        }

        if metadata:
            data.update(dict(metadata))

        if error_type is not None:
            data["error_type"] = _enum_value(error_type) or str(error_type)
        if error_message is not None:
            data["error_message"] = error_message

        return self.add_event(
            job_id=job_id,
            event_type="STATUS_CHANGED",
            data=data,
            commit=commit,
        )

    def list_for_job(self, job_id: int, limit: int = 100) -> list[JobEvent]:
        stmt = (
            select(JobEvent)
            .where(JobEvent.job_id == job_id)
            .order_by(JobEvent.created_at.asc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars().all())


class AuthProfileRepository:
    """Repository for managing authentication profiles."""

    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, profile_id: str) -> Optional[AuthProfile]:
        return self.session.get(AuthProfile, profile_id)

    def list_by_source(self, source_type: SourceType | str) -> list[AuthProfile]:
        stmt = select(AuthProfile).where(AuthProfile.source_type == _enum_value(source_type))
        return list(self.session.execute(stmt).scalars().all())

    def create_or_update(
        self,
        *,
        profile_id: str,
        source_type: SourceType | str,
        cookie_file_path: Optional[str] = None,
        status: AuthProfileStatus | str = AuthProfileStatus.ACTIVE,
    ) -> AuthProfile:
        profile = self.get_by_id(profile_id)
        now = datetime.utcnow()
        if profile is None:
            profile = AuthProfile(
                id=profile_id,
                source_type=_enum_value(source_type),
                cookie_file_path=cookie_file_path,
                status=_enum_value(status) or AuthProfileStatus.ACTIVE.value,
                created_at=now,
                updated_at=now,
            )
            self.session.add(profile)
        else:
            profile.source_type = _enum_value(source_type)
            profile.cookie_file_path = cookie_file_path
            profile.status = _enum_value(status) or profile.status
            profile.updated_at = now

        self.session.commit()
        self.session.refresh(profile)
        return profile

    def mark_success(self, profile: AuthProfile) -> None:
        profile.last_success_at = datetime.utcnow()
        profile.failure_count_recent = 0
        profile.status = AuthProfileStatus.ACTIVE.value
        profile.updated_at = datetime.utcnow()
        self.session.add(profile)
        self.session.commit()
        self.session.refresh(profile)

    def mark_failure(self, profile: AuthProfile) -> None:
        profile.last_failure_at = datetime.utcnow()
        profile.failure_count_recent += 1
        profile.updated_at = datetime.utcnow()
        self.session.add(profile)
        self.session.commit()
        self.session.refresh(profile)

    def get_preferred_profile_for_source(
        self, source_type: SourceType | str
    ) -> Optional[AuthProfile]:
        """Return an active authentication profile for the given source type."""

        stmt = select(AuthProfile).where(
            AuthProfile.source_type == _enum_value(source_type),
            AuthProfile.status == AuthProfileStatus.ACTIVE.value,
        )
        return self.session.execute(stmt).scalars().first()


class ChatSettingsRepository:
    """Repository for chat-specific settings."""

    def __init__(self, session: Session):
        self.session = session

    def get_or_create(self, chat_id: str | int) -> ChatSettings:
        chat_id_str = str(chat_id)
        settings = self.session.get(ChatSettings, chat_id_str)
        if settings is None:
            now = datetime.utcnow()
            settings = ChatSettings(
                chat_id=chat_id_str,
                archive_mode=False,
                default_job_type=JobType.VIDEO.value,
                default_quality="best",
                interactive_hints_enabled=False,
                is_admin=False,
                created_at=now,
                updated_at=now,
            )
            self.session.add(settings)
            self.session.commit()
            self.session.refresh(settings)
        return settings

    def set_archive_mode(self, chat_id: str | int, archive_mode: bool) -> ChatSettings:
        settings = self.get_or_create(chat_id)
        settings.archive_mode = archive_mode
        settings.updated_at = datetime.utcnow()
        self.session.add(settings)
        self.session.commit()
        self.session.refresh(settings)
        return settings

    def set_admin(self, chat_id: str | int, is_admin: bool) -> ChatSettings:
        settings = self.get_or_create(chat_id)
        settings.is_admin = is_admin
        settings.updated_at = datetime.utcnow()
        self.session.add(settings)
        self.session.commit()
        self.session.refresh(settings)
        return settings

    def update_defaults(
        self,
        chat_id: str | int,
        default_job_type: Optional[JobType | str],
        default_quality: Optional[str],
        interactive_hints_enabled: Optional[bool] = None,
    ) -> ChatSettings:
        settings = self.get_or_create(chat_id)
        settings.default_job_type = _enum_value(default_job_type)
        settings.default_quality = default_quality
        if interactive_hints_enabled is not None:
            settings.interactive_hints_enabled = interactive_hints_enabled
        settings.updated_at = datetime.utcnow()
        self.session.add(settings)
        self.session.commit()
        self.session.refresh(settings)
        return settings
