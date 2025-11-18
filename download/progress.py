"""Shared progress hook helpers for yt-dlp downloads."""
from __future__ import annotations

from typing import Callable, Optional

from core.job_service import update_job_progress
from core.logging_utils import get_logger


logger = get_logger(__name__)


def make_yt_progress_hook(
    session_factory,
    job_id: int,
    *,
    extra_callback: Callable[
        [Optional[float], Optional[int], Optional[int], Optional[float]], None
    ]
    | None = None,
):
    """Create a yt-dlp progress hook bound to a job id."""

    def _hook(d: dict) -> None:
        status = d.get("status")
        if status != "downloading":
            return

        downloaded = d.get("downloaded_bytes") or 0
        total = d.get("total_bytes") or d.get("total_bytes_estimate")
        speed_bps = d.get("speed")

        percent = None
        if total:
            try:
                percent = downloaded / total * 100.0
            except ZeroDivisionError:
                percent = None

        update_job_progress(
            session_factory=session_factory,
            job_id=job_id,
            progress_percent=percent,
            downloaded_bytes=downloaded,
            total_bytes=total,
            speed_bps=speed_bps,
        )

        logger.debug(
            "yt-dlp progress update",
            extra={
                "stage": "DOWNLOAD",
                "job_id": job_id,
                "downloaded_bytes": downloaded,
                "total_bytes": total,
                "progress_percent": percent,
                "speed_bps": speed_bps,
            },
        )

        if extra_callback is not None:
            try:
                extra_callback(percent, downloaded, total, speed_bps)
            except Exception:
                logger.exception("Progress callback failed", extra={"stage": "DOWNLOAD"})

    return _hook

