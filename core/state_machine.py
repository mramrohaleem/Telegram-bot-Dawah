"""Centralized job state machine and lifecycle logging."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Mapping

from sqlalchemy.orm import Session

from core.logging_utils import get_logger, log_with_context
from storage.models import ErrorType, Job, JobStatus
from storage.repositories import JobEventRepository

logger = get_logger(__name__)


class InvalidStatusTransition(Exception):
    """Raised when an illegal status transition is attempted."""


ALLOWED_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.PENDING: {JobStatus.QUEUED, JobStatus.FAILED},
    JobStatus.QUEUED: {JobStatus.RUNNING, JobStatus.FAILED},
    JobStatus.RUNNING: {JobStatus.COMPLETED, JobStatus.FAILED},
    JobStatus.COMPLETED: set(),
    JobStatus.FAILED: set(),
}


def _normalize_status(status: JobStatus | str) -> JobStatus:
    return status if isinstance(status, JobStatus) else JobStatus(status)


def _normalize_error_type(error_type: ErrorType | str | None) -> ErrorType | None:
    if error_type is None:
        return None
    return error_type if isinstance(error_type, ErrorType) else ErrorType(error_type)


def transition_status(
    session: Session,
    job: Job,
    to_status: JobStatus,
    *,
    metadata: Mapping[str, Any] | None = None,
    error_type: ErrorType | None = None,
    error_message: str | None = None,
) -> Job:
    """Transition a job to a new status with validation and lifecycle logging."""

    current_status = _normalize_status(job.status)
    new_status = _normalize_status(to_status)

    allowed = ALLOWED_TRANSITIONS.get(current_status, set())
    if new_status not in allowed:
        log_with_context(
            logger,
            logging.ERROR,
            "Invalid status transition attempted",
            job_id=job.id,
            old_status=current_status.value,
            new_status=new_status.value,
            stage="STATE_MACHINE",
        )
        raise InvalidStatusTransition(
            f"Cannot transition job {job.id} from {current_status.value} to {new_status.value}"
        )

    normalized_error_type = _normalize_error_type(error_type)

    job.status = new_status.value
    if normalized_error_type is not None:
        job.error_type = normalized_error_type.value
    if error_message is not None:
        job.error_message = error_message
    job.updated_at = datetime.utcnow()

    event_repo = JobEventRepository(session)
    event_repo.add_status_change_event(
        job_id=job.id,
        old_status=current_status,
        new_status=new_status,
        metadata=metadata,
        error_type=normalized_error_type,
        error_message=error_message,
        commit=False,
    )

    session.add(job)
    session.commit()
    session.refresh(job)

    log_with_context(
        logger,
        logging.INFO,
        "Job status changed",
        job_id=job.id,
        old_status=current_status.value,
        new_status=new_status.value,
        error_type=job.error_type,
        stage="STATE_MACHINE",
    )

    return job


def mark_job_queued(
    session: Session, job: Job, *, metadata: Mapping[str, Any] | None = None
) -> Job:
    return transition_status(session, job, JobStatus.QUEUED, metadata=metadata)


def mark_job_running(
    session: Session, job: Job, *, metadata: Mapping[str, Any] | None = None
) -> Job:
    return transition_status(session, job, JobStatus.RUNNING, metadata=metadata)


def mark_job_completed(
    session: Session, job: Job, *, metadata: Mapping[str, Any] | None = None
) -> Job:
    return transition_status(session, job, JobStatus.COMPLETED, metadata=metadata)


def mark_job_failed(
    session: Session,
    job: Job,
    *,
    metadata: Mapping[str, Any] | None = None,
    error_type: ErrorType | None = None,
    error_message: str | None = None,
) -> Job:
    return transition_status(
        session,
        job,
        JobStatus.FAILED,
        metadata=metadata,
        error_type=error_type,
        error_message=error_message,
    )
