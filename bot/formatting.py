"""Formatting helpers for Telegram messages."""
from __future__ import annotations

from bot import texts
from storage.models import Job, JobType, JobStatus


def _type_label(job_type: str | None) -> str:
    if job_type == JobType.VIDEO.value or job_type == JobType.VIDEO:
        return "فيديو"
    if job_type == JobType.AUDIO.value or job_type == JobType.AUDIO:
        return "صوت"
    return "غير معروف"


def _quality_label(quality: str | None) -> str:
    if not quality:
        return "أفضل جودة"
    if quality == "best":
        return "أفضل جودة"
    if quality == "audio_best":
        return "أفضل جودة صوت"
    if quality.endswith("kbps") or quality.endswith("k"):
        return quality.replace("k", " kbps") if quality.endswith("k") else quality
    return quality


def _status_label(status: str | None) -> str:
    if status == JobStatus.PENDING.value:
        return "في انتظار المعالجة ⏳"
    if status == JobStatus.QUEUED.value:
        return "في قائمة الانتظار ⏳"
    if status == JobStatus.RUNNING.value:
        return "جاري التحميل ⬇️"
    if status == JobStatus.COMPLETED.value:
        return "تم التسليم ✅"
    if status == JobStatus.FAILED.value:
        return "فشل ❌"
    return status or "غير معروف"


def format_job_status(job: Job) -> str:
    """Return a concise, single-line job status summary in Arabic."""

    type_label = _type_label(job.job_type)
    quality_label = _quality_label(job.requested_quality)
    percent_str = "-" if job.progress_percent is None else f"{job.progress_percent:.0f}%"

    speed_bps = getattr(job, "download_speed_bps", None)
    if speed_bps:
        mb_per_s = speed_bps / (1024 * 1024)
        speed_str = f"{mb_per_s:.1f} MB/s"
    else:
        speed_str = "-"

    status_text = _status_label(job.status)
    error_type = getattr(job, "error_type", None)
    if job.status == JobStatus.FAILED.value and error_type:
        reason = texts.failure_reason_label(error_type)
        if reason:
            status_text = f"{status_text} ({reason})"

    return (
        f"#{job.id} | {type_label} | {quality_label} | "
        f"{percent_str} | {speed_str} | {status_text}"
    )

