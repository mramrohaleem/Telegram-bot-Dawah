from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional, Tuple
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
from storage.models import Job, JobDraft, JobStatus, JobType, SourceType
from storage.repositories import (
    ChatSettingsRepository,
    JobEventRepository,
    JobDraftRepository,
    JobRepository,
)

logger = get_logger(__name__)


class JobCreationError(Exception):
    """Raised when a job cannot be created due to validation or unsupported source."""


class JobService:
    """Coordinates URL parsing, validation, drafts, and job persistence."""

    def __init__(self, session_factory: sessionmaker[Session]):
        self._session_factory = session_factory

    def _get_session(self) -> Session:
        return self._session_factory()

    def create_draft_from_message(
        self,
        *,
        chat_id: int | str,
        user_id: Optional[int | str],
        text: str,
    ) -> JobDraft:
        """Parse a Telegram message, validate URL, detect source, and create a draft."""

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
                source_type = SourceType.DIRECT_MEDIA
            else:
                raise JobCreationError("Unsupported source for provided URL")

        session = self._get_session()
        try:
            draft_repo = JobDraftRepository(session)
            draft = draft_repo.create_draft(
                chat_id=str(chat_id),
                user_id=str(user_id) if user_id is not None else None,
                url=validated_url,
                source_type=source_type,
                url_domain=domain,
            )
            log_with_context(
                logger,
                logging.INFO,
                "Created draft from message",
                stage="JOB_SERVICE",
                draft_id=draft.id,
                chat_id=chat_id,
                user_id=user_id,
                source_type=source_type.value,
                url_domain=domain,
            )
            return draft
        except JobCreationError:
            session.rollback()
            raise
        except Exception as exc:  # pragma: no cover - defensive logging
            session.rollback()
            logger.exception("Unexpected error creating draft")
            raise JobCreationError("Unexpected error while creating job draft") from exc
        finally:
            session.close()

    def create_job_from_message(
        self,
        *,
        chat_id: int | str,
        user_id: Optional[int | str],
        text: str,
        forced_job_type: JobType | None = None,
        forced_quality: str | None = None,
    ) -> Job:
        """Backward-compatible helper to create a job directly from message text."""

        draft = self.create_draft_from_message(
            chat_id=chat_id,
            user_id=user_id,
            text=text,
        )

        session = self._get_session()
        try:
            settings_repo = ChatSettingsRepository(session)
            settings = settings_repo.get_or_create(chat_id)
            job_type = forced_job_type or self._resolve_job_type(settings)
            requested_quality = forced_quality or settings.default_quality or "best"
        finally:
            session.close()

        job, _, _ = self.create_job_from_draft(
            draft,
            media_type=job_type,
            quality_slug=requested_quality,
        )
        return job

    def create_job_from_draft(
        self,
        draft: JobDraft,
        *,
        media_type: JobType | str,
        quality_slug: str,
    ) -> Tuple[Job, bool, bool]:
        """Create a Job from a draft while avoiding duplicates.

        Returns (job, reused_existing, reused_from_archive).
        """

        job_type = self._resolve_job_type_from_input(media_type)
        requested_quality = quality_slug or "best"

        session = self._get_session()
        try:
            job_repo = JobRepository(session)
            event_repo = JobEventRepository(session)

            normalized_url = normalize_url(draft.url)
            job_key = self._build_job_key(
                source_type=SourceType(draft.source_type),
                normalized_url=normalized_url,
                job_type=job_type,
                requested_quality=requested_quality,
            )

            existing_job = job_repo.get_by_job_key(job_key)
            if existing_job:
                reused_from_archive = False
                if (
                    existing_job.status == JobStatus.COMPLETED.value
                    and existing_job.file_path
                ):
                    reused_from_archive = True

                event_repo.add_event(
                    existing_job.id,
                    "JOB_REUSED",
                    {"url": draft.url, "job_key": job_key},
                    commit=False,
                )
                session.commit()
                session.refresh(existing_job)
                log_with_context(
                    logger,
                    logging.INFO,
                    "Reusing existing job for draft",
                    stage="JOB_SERVICE",
                    job_id=existing_job.id,
                    draft_id=draft.id,
                    chat_id=draft.chat_id,
                    user_id=draft.user_id,
                    source_type=draft.source_type,
                    job_type=job_type.value,
                    requested_quality=requested_quality,
                    job_key=job_key,
                )
                return existing_job, True, reused_from_archive

            job = job_repo.create_job(
                url=draft.url,
                source_type=SourceType(draft.source_type),
                job_type=job_type,
                requested_quality=requested_quality,
                job_key=job_key,
                user_id=draft.user_id,
                chat_id=draft.chat_id,
                commit=False,
            )

            if draft.suggested_title:
                job.final_title = draft.suggested_title

            event_repo.add_event(
                job.id,
                "JOB_CREATED",
                {
                    "url": draft.url,
                    "source_type": draft.source_type,
                    "job_type": job_type.value,
                    "requested_quality": requested_quality,
                    "draft_id": draft.id,
                },
                commit=False,
            )

            session.commit()
            session.refresh(job)

            log_with_context(
                logger,
                logging.INFO,
                "Created job from draft",
                stage="JOB_SERVICE",
                job_id=job.id,
                draft_id=draft.id,
                chat_id=draft.chat_id,
                user_id=draft.user_id,
                source_type=draft.source_type,
                job_type=job_type.value,
                requested_quality=requested_quality,
                job_key=job_key,
            )
            return job, False, False
        except JobCreationError:
            session.rollback()
            raise
        except Exception as exc:  # pragma: no cover - defensive logging
            session.rollback()
            logger.exception("Unexpected error creating job from draft")
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

    def list_recent_jobs(self, chat_id: str | int, limit: int = 10) -> list[Job]:
        session = self._get_session()
        try:
            repo = JobRepository(session)
            return repo.list_recent_for_chat(chat_id, limit=limit)
        finally:
            session.close()

    def list_jobs_for_status_view(
        self, chat_id: str | int, *, recent_completed_limit: int = 3
    ) -> tuple[list[Job], list[Job]]:
        session = self._get_session()
        try:
            repo = JobRepository(session)
            active = repo.list_active_for_chat(chat_id)
            recent_completed = repo.list_recent_completed_for_chat(
                chat_id, limit=recent_completed_limit
            )
            return active, recent_completed
        finally:
            session.close()

    def _resolve_job_type(self, settings) -> JobType:
        if settings.default_job_type:
            try:
                return JobType(settings.default_job_type)
            except ValueError:
                pass
        return JobType.VIDEO

    def _resolve_job_type_from_input(self, value: JobType | str) -> JobType:
        if isinstance(value, JobType):
            return value
        try:
            return JobType(value)
        except ValueError:
            return JobType.VIDEO

    def _is_direct_media_url(self, url: str) -> bool:
        parsed = urlparse(url)
        path = parsed.path.lower()
        return path.endswith(
            (".mp3", ".mp4", ".m4a", ".webm", ".wav", ".mkv")
        )

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


def update_job_progress(
    session_factory: sessionmaker[Session],
    job_id: int,
    *,
    progress_percent: Optional[float],
    downloaded_bytes: Optional[int],
    total_bytes: Optional[int],
    speed_bps: Optional[float],
) -> None:
    """Update progress metrics for a running job."""

    session = session_factory()
    try:
        repo = JobRepository(session)
        job = repo.get_by_id(job_id)
        if job is None:
            return
        job.progress_percent = progress_percent
        job.downloaded_bytes = downloaded_bytes
        job.total_bytes = total_bytes
        job.download_speed_bps = speed_bps
        job.last_progress_at = datetime.utcnow()
        session.add(job)
        session.commit()
    except Exception as exc:  # pragma: no cover - defensive logging
        session.rollback()
        log_with_context(
            logger,
            logging.ERROR,
            "Failed to update job progress",
            stage="JOB_SERVICE",
            job_id=job_id,
            error=str(exc),
        )
    finally:
        session.close()
