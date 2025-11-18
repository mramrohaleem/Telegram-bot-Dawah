from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from bot.formatting import format_job_status
from core.job_service import update_job_progress
from storage.db import Base
from storage.models import JobStatus, JobType, SourceType
from storage.repositories import JobRepository


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=Session, autoflush=False)


def test_format_job_status_includes_progress_and_speed():
    job = SimpleNamespace(
        id=5,
        job_type=JobType.VIDEO.value,
        requested_quality="720p",
        status=JobStatus.RUNNING.value,
        progress_percent=64.4,
        download_speed_bps=1.5 * 1024 * 1024,
        error_type=None,
    )

    text = format_job_status(job)

    assert "#5" in text
    assert "فيديو" in text
    assert "720p" in text
    assert "التقدم" in text
    assert "██" in text  # progress bar blocks
    assert "64%" in text
    assert "1.5 MB/s" in text
    assert "جاري التحميل" in text


def test_update_job_progress_throttles(monkeypatch, session_factory):
    session = session_factory()
    repo = JobRepository(session)
    job = repo.create_job(
        url="https://youtu.be/test",
        source_type=SourceType.YOUTUBE,
        job_type=JobType.AUDIO,
        requested_quality="best",
        job_key="yt:test:AUDIO:best",
        chat_id="1",
    )
    job_id = job.id
    session.close()

    base_time = datetime(2024, 1, 1, 12, 0, 0)

    class FrozenDateTime(datetime):
        current = base_time

        @classmethod
        def utcnow(cls):
            return cls.current

    monkeypatch.setattr("core.job_service.datetime", FrozenDateTime)

    update_job_progress(
        session_factory,
        job_id,
        progress_percent=10.0,
        downloaded_bytes=100,
        total_bytes=1000,
        speed_bps=100.0,
    )

    FrozenDateTime.current = base_time + timedelta(seconds=0.5)
    update_job_progress(
        session_factory,
        job_id,
        progress_percent=10.4,
        downloaded_bytes=150,
        total_bytes=1000,
        speed_bps=200.0,
    )

    check_session = session_factory()
    try:
        refreshed = JobRepository(check_session).get_by_id(job_id)
        assert refreshed.progress_percent == pytest.approx(10.0)
        first_timestamp = refreshed.last_progress_at
    finally:
        check_session.close()

    FrozenDateTime.current = base_time + timedelta(seconds=2)
    update_job_progress(
        session_factory,
        job_id,
        progress_percent=12.0,
        downloaded_bytes=200,
        total_bytes=1000,
        speed_bps=300.0,
    )

    final_session = session_factory()
    try:
        refreshed = JobRepository(final_session).get_by_id(job_id)
        assert refreshed.progress_percent == pytest.approx(12.0)
        assert refreshed.downloaded_bytes == 200
        assert refreshed.total_bytes == 1000
        assert refreshed.download_speed_bps == pytest.approx(300.0)
        assert refreshed.last_progress_at > first_timestamp
    finally:
        final_session.close()

