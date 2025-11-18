"""Formatting helpers for Telegram messages."""
from __future__ import annotations

from typing import Any

from bot import texts
from storage.models import JobStatus, JobType

TYPE_LABELS: dict[JobType, str] = {
    JobType.VIDEO: "فيديو",
    JobType.AUDIO: "صوت",
}

STATUS_LABELS: dict[JobStatus, str] = {
    JobStatus.PENDING: "في انتظار المعالجة ⏳",
    JobStatus.QUEUED: "في قائمة الانتظار ⏳",
    JobStatus.RUNNING: "جاري التحميل ⬇️",
    JobStatus.COMPLETED: "تم التسليم ✅",
    JobStatus.FAILED: "فشل ❌",
}


def _normalize_enum(value: Any, enum_cls):
    try:
        return enum_cls(value)
    except Exception:
        return None


def _type_label(job_type: str | JobType | None) -> str:
    enum_value = _normalize_enum(job_type, JobType)
    if enum_value:
        return TYPE_LABELS.get(enum_value, "غير معروف")
    return "غير معروف"


def _quality_label(quality: str | None) -> str:
    if not quality or quality == "best":
        return "أفضل جودة"
    if quality == "audio_best":
        return "أفضل جودة صوت"
    if quality.endswith("kbps") or quality.endswith("k"):
        return quality.replace("k", " kbps") if quality.endswith("k") else quality
    return quality


def _status_label(status: str | JobStatus | None) -> str:
    enum_value = _normalize_enum(status, JobStatus)
    if enum_value:
        return STATUS_LABELS.get(enum_value, enum_value.value)
    return status or "غير معروف"


def _progress_bar(percent: float | None, length: int = 10) -> str:
    if percent is None:
        return f"[{'░' * length}]"
    clamped = max(0.0, min(100.0, percent))
    filled = min(length, max(0, int(round((clamped / 100.0) * length))))
    empty = max(0, length - filled)
    return f"[{'█' * filled}{'░' * empty}]"


def _speed_label(speed_bps: float | None) -> str | None:
    if not speed_bps or speed_bps <= 0:
        return None
    mb_per_s = speed_bps / (1024 * 1024)
    return f"{mb_per_s:.1f} MB/s"


def format_job_status(job: Any) -> str:
    """Return a detailed, multi-line job status summary in Arabic."""

    type_label = _type_label(getattr(job, "job_type", None))
    quality_label = _quality_label(getattr(job, "requested_quality", None))
    status_text = _status_label(getattr(job, "status", None))

    error_type = getattr(job, "error_type", None)
    if status_text.startswith("فشل") and error_type:
        reason = texts.failure_reason_label(error_type)
        if reason:
            status_text = f"{status_text} ({reason})"

    header = f"#{job.id} | {type_label} | {quality_label}"
    lines = [header, f"الحالة: {status_text}"]

    progress_percent = getattr(job, "progress_percent", None)
    bar = _progress_bar(progress_percent)
    if progress_percent is None:
        lines.append(f"التقدم: {bar} -")
    else:
        lines.append(f"التقدم: {bar} {progress_percent:.0f}%")

    speed_str = _speed_label(getattr(job, "download_speed_bps", None))
    if speed_str:
        lines.append(f"السرعة: {speed_str}")

    return "\n".join(lines)
