"""Orchestration helpers for creating jobs from Telegram messages."""
from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urlparse

from sqlalchemy.orm import Session, sessionmaker

from core.logging_utils import get_logger, log_with_context
from core.source_detection import detect_source_type
from core.url_utils import (
    InvalidUrlError,
    extract_first_url_from_text,
    get_url_domain,
    normalize_url,
    validate_url,
)
from storage.models import Job, JobType, SourceType
from storage.repositories import (
    ChatSettingsRepository,
    JobEventRepository,
    JobRepository,
)

logger = get_logger(__name__)


class JobCreationError(Exception):
    """Raised when a job cannot be created due to validation or unsupported source."""


class JobService:
    """Coordinates URL parsing, validation, and job persistence."""

    def __init__(self, session_factory: sessionmaker[Session]):
        self._session_factory = session_factory

    def _get_session(self) -> Session:
        return self._session_factory()

    def create_job_from_message(
        self,
        *,
        chat_id: int | str,
        user_id: Optional[int | str],
        text: str,
    ) -> Job:
        """Parse a Telegram message, validate URL, detect source, and create a Job."""

        if not text:
            raise JobCreationError("Message text is empty")

        url = extract_first_url_from_text(text)
        if not url:
            raise JobCreationError("No URL found in message")

        try:
            validated_url = validate_url(url)
        except InvalidUrlError as exc:
            raise JobCreationError(str(exc)) from exc

        domain = get_url_domain(validated_url)
        source_type = detect_source_type(domain)
        if source_type is None:
            if self._is_direct_media_url(validated_url):
                source_type = SourceType.GENERIC
            else:
                raise JobCreationError("Unsupported source for provided URL")

        session = self._get_session()
        try:
            chat_settings_repo = ChatSettingsRepository(session)
            job_repo = JobRepository(session)
            event_repo = JobEventRepository(session)

            settings = chat_settings_repo.get_or_create(chat_id)
            job_type = self._resolve_job_type(settings)
            requested_quality = settings.default_quality or "best"

            normalized_url = normalize_url(validated_url)
            job_key = self._build_job_key(
                source_type=source_type,
                normalized_url=normalized_url,
                job_type=job_type,
                requested_quality=requested_quality,
            )

            existing_job = job_repo.get_by_job_key(job_key)
            if existing_job:
                event_repo.add_event(
                    existing_job.id,
                    "JOB_REUSED",
                    {"url": validated_url, "job_key": job_key},
                    commit=False,
                )
                session.commit()
                session.refresh(existing_job)
                log_with_context(
                    logger,
                    logging.INFO,
                    "Reusing existing job for matching job key",
                    stage="JOB_SERVICE",
                    job_id=existing_job.id,
                    chat_id=chat_id,
                    user_id=user_id,
                    source_type=source_type.value,
                    job_type=job_type.value,
                    requested_quality=requested_quality,
                    url_domain=domain,
                    job_key=job_key,
                )
                return existing_job

            job = job_repo.create_job(
                url=validated_url,
                source_type=source_type,
                job_type=job_type,
                requested_quality=requested_quality,
                job_key=job_key,
                user_id=str(user_id) if user_id is not None else None,
                chat_id=str(chat_id),
                commit=False,
            )

            event_repo.add_event(
                job.id,
                "JOB_CREATED",
                {
                    "url": validated_url,
                    "source_type": source_type.value,
                    "job_type": job_type.value,
                    "requested_quality": requested_quality,
                },
                commit=False,
            )

            session.commit()
            session.refresh(job)

            log_with_context(
                logger,
                logging.INFO,
                "Created job from message",
                stage="JOB_SERVICE",
                job_id=job.id,
                chat_id=chat_id,
                user_id=user_id,
                source_type=source_type.value,
                job_type=job_type.value,
                requested_quality=requested_quality,
                url_domain=domain,
                job_key=job_key,
            )
            return job
        except JobCreationError:
            session.rollback()
            raise
        except Exception as exc:  # pragma: no cover - defensive logging
            session.rollback()
            logger.exception("Unexpected error creating job")
            raise JobCreationError("Unexpected error while creating job") from exc
        finally:
            session.close()

    def get_job_by_id(self, job_id: int) -> Optional[Job]:
        """Return a job by id if present."""

        session = self._get_session()
        try:
            repo = JobRepository(session)
            return repo.get_by_id(job_id)
        finally:
            session.close()

    def _resolve_job_type(self, settings) -> JobType:
        if settings.default_job_type:
            try:
                return JobType(settings.default_job_type)
            except ValueError:
                pass
        return JobType.AUDIO

    def _is_direct_media_url(self, url: str) -> bool:
        parsed = urlparse(url)
        path = parsed.path.lower()
        return path.endswith((".mp3", ".mp4", ".m4a", ".webm", ".wav"))

    def _build_job_key(
        self,
        *,
        source_type: SourceType,
        normalized_url: str,
        job_type: JobType,
        requested_quality: Optional[str],
    ) -> str:
        quality = requested_quality or ""
        return f"{source_type.value}:{normalized_url}:{job_type.value}:{quality}"
