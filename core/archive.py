"""Archive utilities for moving completed job files into retention storage."""
from __future__ import annotations

import os
import shutil
from datetime import datetime
import logging

from config.settings import Settings
from core.logging_utils import get_logger, log_with_context
from storage.models import Job
from storage.repositories import ChatSettingsRepository, JobEventRepository, JobRepository

logger = get_logger(__name__)


def maybe_archive_job_file(
    *,
    settings: Settings,
    job_repo: JobRepository,
    chat_settings_repo: ChatSettingsRepository,
    job: Job,
) -> None:
    """Move a completed job file into ARCHIVE_ROOT when archive mode is enabled."""

    if not job.file_path:
        return

    if job.chat_id is None:
        return

    chat_settings = chat_settings_repo.get_or_create(job.chat_id)
    if not chat_settings.archive_mode:
        return

    if job.is_archived:
        return

    if not os.path.exists(job.file_path):
        log_with_context(
            logger,
            level=logging.WARNING,
            message="Job file missing, cannot archive",
            stage="ARCHIVE",
            job_id=job.id,
            file_path=job.file_path,
        )
        return

    source_type = job.source_type or "unknown"
    now = datetime.utcnow()
    dest_dir = os.path.join(
        settings.archive_root,
        source_type.lower(),
        str(job.chat_id),
        now.strftime("%Y"),
        now.strftime("%m"),
    )
    os.makedirs(dest_dir, exist_ok=True)

    filename = os.path.basename(job.file_path)
    destination_path = os.path.join(dest_dir, filename)

    old_path = job.file_path
    try:
        shutil.move(job.file_path, destination_path)
    except Exception as exc:  # pragma: no cover - defensive
        log_with_context(
            logger,
            level=logging.ERROR,
            message="Failed to move file to archive",
            stage="ARCHIVE",
            job_id=job.id,
            old_path=old_path,
            new_path=destination_path,
            error=str(exc),
        )
        return

    job.file_path = destination_path
    job.is_archived = True
    job.archived_at = now
    job.updated_at = datetime.utcnow()

    event_repo = JobEventRepository(job_repo.session)
    event_repo.add_event(
        job.id,
        "ARCHIVED",
        {"old_path": old_path, "new_path": destination_path},
        commit=False,
    )

    log_with_context(
        logger,
        level=logging.INFO,
        message="Archived job file",
        stage="ARCHIVE",
        job_id=job.id,
        old_path=old_path,
        new_path=destination_path,
    )

    job_repo.session.add(job)

