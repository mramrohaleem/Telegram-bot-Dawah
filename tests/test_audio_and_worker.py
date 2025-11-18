import asyncio
import os
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from config.settings import Settings
from core.job_service import JobService, update_job_progress
from core.state_machine import mark_job_queued, mark_job_running
from core.worker import _engine, _process_job
from download.base import DownloadError, DownloadResult
from storage.db import Base
from storage.models import ErrorType, JobStatus, JobType, SourceType
from storage.repositories import JobDraftRepository, JobRepository


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=Session, autoflush=False)


@pytest.fixture()
def settings(tmp_path):
    base = tmp_path
    return Settings(
        db_path=str(base / "db.sqlite3"),
        tmp_root=str(base / "tmp"),
        archive_root=str(base / "archive"),
        auth_profile_dir=str(base / "auth"),
        telegram_bot_token="TEST",
        mock_downloads=False,
        max_parallel_jobs=2,
        max_queue_length=10,
        worker_poll_interval_seconds=0,
        delivery_poll_interval_seconds=0,
    )


@pytest.fixture(autouse=True)
def ensure_dirs(settings):
    os.makedirs(settings.tmp_root, exist_ok=True)
    os.makedirs(settings.archive_root, exist_ok=True)
    os.makedirs(settings.auth_profile_dir, exist_ok=True)
    yield


def test_audio_job_created_with_type_and_quality(session_factory):
    job_service = JobService(session_factory)
    session = session_factory()
    try:
        drafts = JobDraftRepository(session)
        draft = drafts.create_draft(
            chat_id="1",
            user_id="2",
            url="https://youtu.be/test",
            source_type=SourceType.YOUTUBE,
            url_domain="youtu.be",
        )
    finally:
        session.close()

    job, reused, _ = job_service.create_job_from_draft(
        draft, media_type=JobType.AUDIO.value, quality_slug="128k"
    )

    assert job.job_type == JobType.AUDIO.value
    assert job.requested_quality == "128k"
    assert "AUDIO" in job.job_key
    assert not reused


class _FakeResult(DownloadResult):
    def __init__(
        self,
        *,
        url: str,
        file_path: str,
        title: str = "title",
        filesize: int = 1024,
        thumbnail_path: str | None = None,
    ):
        super().__init__(
            url=url,
            file_path=file_path,
            final_ext=os.path.splitext(file_path)[1].lstrip("."),
            title=title,
            thumbnail_url=None,
            thumbnail_path=thumbnail_path,
            filesize=filesize,
            metadata=None,  # type: ignore[arg-type]
        )


def test_worker_process_audio_success(monkeypatch, session_factory, settings, tmp_path):
    session = session_factory()
    repo = JobRepository(session)
    job = repo.create_job(
        url="https://youtu.be/test",
        source_type=SourceType.YOUTUBE,
        job_type=JobType.AUDIO,
        requested_quality="audio_best",
        job_key="yt:test:AUDIO:audio_best",
        chat_id="1",
    )
    mark_job_queued(session, job, metadata={"reason": "test"})
    mark_job_running(session, job, metadata={"reason": "test"})
    job_id = job.id
    session.close()

    temp_file = tmp_path / "audio.m4a"
    temp_file.write_text("data")

    fake_result = _FakeResult(url=job.url, file_path=str(temp_file), filesize=temp_file.stat().st_size)

    def _fake_download_job(**kwargs):
        return fake_result

    monkeypatch.setattr(_engine, "download_job", _fake_download_job)

    asyncio.run(_process_job(settings, session_factory, job_id))

    check_session = session_factory()
    try:
        refreshed = JobRepository(check_session).get_by_id(job_id)
        assert refreshed.status == JobStatus.COMPLETED.value
        assert refreshed.file_path == str(temp_file)
        assert refreshed.progress_percent == 100.0
        assert refreshed.downloaded_bytes == temp_file.stat().st_size
    finally:
        check_session.close()


def test_worker_recovers_after_failure(monkeypatch, session_factory, settings, tmp_path):
    session = session_factory()
    repo = JobRepository(session)
    failing = repo.create_job(
        url="https://youtu.be/fail",
        source_type=SourceType.YOUTUBE,
        job_type=JobType.AUDIO,
        requested_quality="128k",
        job_key="yt:fail:AUDIO:128k",
        chat_id="1",
    )
    succeeding = repo.create_job(
        url="https://youtu.be/success",
        source_type=SourceType.YOUTUBE,
        job_type=JobType.AUDIO,
        requested_quality="best",
        job_key="yt:success:AUDIO:best",
        chat_id="1",
    )
    mark_job_queued(session, failing, metadata={"reason": "test"})
    mark_job_running(session, failing, metadata={"reason": "test"})
    mark_job_queued(session, succeeding, metadata={"reason": "test"})
    mark_job_running(session, succeeding, metadata={"reason": "test"})
    failing_id = failing.id
    succeeding_id = succeeding.id
    session.close()

    temp_file = tmp_path / "ok.m4a"
    temp_file.write_text("ok")
    success_result = _FakeResult(url=succeeding.url, file_path=str(temp_file), filesize=temp_file.stat().st_size)

    calls = {"count": 0}

    def _fake_download_job(**kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise DownloadError(error_type=ErrorType.NETWORK_ERROR, message="network down")
        return success_result

    monkeypatch.setattr(_engine, "download_job", _fake_download_job)

    asyncio.run(_process_job(settings, session_factory, failing_id))
    asyncio.run(_process_job(settings, session_factory, succeeding_id))

    check_session = session_factory()
    try:
        repo = JobRepository(check_session)
        failed = repo.get_by_id(failing_id)
        succeeded = repo.get_by_id(succeeding_id)
        assert failed.status == JobStatus.FAILED.value
        assert failed.error_type == ErrorType.NETWORK_ERROR.value
        assert succeeded.status == JobStatus.COMPLETED.value
    finally:
        check_session.close()


def test_progress_updates_persist(session_factory):
    session = session_factory()
    repo = JobRepository(session)
    job = repo.create_job(
        url="https://youtu.be/test",
        source_type=SourceType.YOUTUBE,
        job_type=JobType.AUDIO,
        requested_quality="best",
        job_key="yt:test:AUDIO:best",
    )
    session.close()

    update_job_progress(
        session_factory,
        job.id,
        progress_percent=42.5,
        downloaded_bytes=1024,
        total_bytes=2048,
        speed_bps=1024 * 1024,
    )

    check_session = session_factory()
    try:
        refreshed = JobRepository(check_session).get_by_id(job.id)
        assert refreshed.progress_percent == pytest.approx(42.5)
        assert refreshed.downloaded_bytes == 1024
        assert refreshed.total_bytes == 2048
        assert refreshed.download_speed_bps == pytest.approx(1024 * 1024)
    finally:
        check_session.close()


def test_status_formatting_with_progress():
    from bot.formatting import format_job_status

    job = SimpleNamespace(
        id=7,
        job_type=JobType.AUDIO.value,
        requested_quality="128k",
        status=JobStatus.RUNNING.value,
        progress_percent=75.2,
        download_speed_bps=3.2 * 1024 * 1024,
        error_type=None,
    )

    line = format_job_status(job)

    assert "#7" in line
    assert "صوت" in line
    assert "75%" in line
    assert "3.2 MB/s" in line


def test_failed_status_includes_reason():
    from bot.formatting import format_job_status

    job = SimpleNamespace(
        id=9,
        job_type=JobType.AUDIO.value,
        requested_quality="best",
        status=JobStatus.FAILED.value,
        progress_percent=None,
        download_speed_bps=None,
        error_type=ErrorType.NETWORK_ERROR.value,
    )

    line = format_job_status(job)

    assert "فشل" in line
    assert "الشبكة" in line
