from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Callable, Optional

from yt_dlp import YoutubeDL
from yt_dlp import utils as ydl_utils

from core.logging_utils import get_logger, log_with_context
from download.base import BaseDownloader, DownloadError, DownloadResult, MetadataResult
from storage.models import ErrorType, JobType

logger = get_logger(__name__)


def _build_format_selector(job_type: JobType, requested_quality: Optional[str]) -> str:
    if job_type == JobType.AUDIO:
        return "bestaudio/best"

    if requested_quality and requested_quality.endswith("p"):
        try:
            height = int(requested_quality[:-1])
            return (
                f"bestvideo[height<={height}][ext=mp4]+bestaudio/best"
                f"[height<={height}]/best"
            )
        except ValueError:
            pass

    return "bestvideo[ext=mp4]+bestaudio/best/best"


def _extract_filesize(info: dict[str, Any]) -> Optional[int]:
    size = info.get("filesize") or info.get("filesize_approx")
    if size:
        return int(size)
    for fmt in info.get("formats", []) or []:
        if fmt.get("filesize"):
            return int(fmt["filesize"])
        if fmt.get("filesize_approx"):
            return int(fmt["filesize_approx"])
    return None


def _build_progress_hook(
    progress_callback: Callable[[Optional[float], Optional[int], Optional[int], Optional[float]], None]
):
    def _hook(d: dict[str, Any]) -> None:
        if d.get("status") != "downloading":
            return
        downloaded = d.get("downloaded_bytes")
        total = d.get("total_bytes") or d.get("total_bytes_estimate")
        speed = d.get("speed")
        percent = None
        if total and total > 0 and downloaded is not None:
            percent = downloaded * 100.0 / float(total)
        try:
            progress_callback(percent, downloaded, total, speed)
        except Exception:
            logger.exception("Progress callback failed", extra={"stage": "DOWNLOAD"})

    return _hook


def _map_error(exc: Exception) -> tuple[ErrorType, Optional[int]]:
    message = str(exc).lower()
    http_status: Optional[int] = None

    status_match = re.search(r"http error (\d{3})", message)
    if status_match:
        http_status = int(status_match.group(1))

    if isinstance(exc, ydl_utils.GeoRestrictedError):
        return ErrorType.GEO_BLOCK, http_status
    if isinstance(exc, ydl_utils.ExtractorError):
        if "login" in message or "signin" in message:
            return ErrorType.AUTH_ERROR, http_status
        if "unsupported" in message:
            return ErrorType.UNSUPPORTED_SOURCE, http_status
        if "drm" in message or "protected" in message:
            return ErrorType.PROTECTED_CONTENT, http_status
        if "update" in message:
            return ErrorType.EXTRACTOR_UPDATE_REQUIRED, http_status
        return ErrorType.EXTRACTOR_ERROR, http_status
    if isinstance(exc, ydl_utils.DownloadError):
        if http_status == 429 or "too many requests" in message:
            return ErrorType.RATE_LIMIT, http_status
        if http_status in {401, 403}:
            return ErrorType.AUTH_ERROR, http_status
        if http_status and 400 <= http_status < 500:
            return ErrorType.HTTP_ERROR, http_status
        if http_status and http_status >= 500:
            return ErrorType.HTTP_ERROR, http_status
        if "network" in message or "connection" in message:
            return ErrorType.NETWORK_ERROR, http_status
        return ErrorType.UNKNOWN, http_status
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return ErrorType.NETWORK_ERROR, http_status

    if "cookie" in message or "login" in message:
        return ErrorType.AUTH_ERROR, http_status
    return ErrorType.UNKNOWN, http_status


class GenericYtDlpDownloader(BaseDownloader):
    """Downloader that supports multiple sites via yt-dlp."""

    def __init__(self, name: str) -> None:
        self.name = name

    def _base_options(
        self, *, cookie_file: str | None = None, target_dir: str | None = None
    ) -> dict[str, Any]:
        outtmpl = None
        if target_dir:
            outtmpl = os.path.join(target_dir, "%(title)s.%(ext)s")
        opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
        }
        if outtmpl:
            opts["outtmpl"] = {"default": outtmpl}
        if cookie_file:
            opts["cookiefile"] = cookie_file
        return opts

    def fetch_metadata(
        self,
        *,
        url: str,
        job_type: JobType,
        requested_quality: str | None,
        cookie_file: str | None = None,
    ) -> MetadataResult:
        options = self._base_options(cookie_file=cookie_file)
        log_with_context(
            logger,
            level=logging.INFO,
            message="Fetching metadata",
            stage="DOWNLOAD",
            downloader=self.name,
            url=url,
            job_type=job_type,
            requested_quality=requested_quality,
            has_cookie=bool(cookie_file),
        )
        try:
            with YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as exc:  # pragma: no cover - classification done below
            error_type, http_status = _map_error(exc)
            log_with_context(
                logger,
                level=logging.ERROR,
                message="Metadata fetch failed",
                stage="DOWNLOAD",
                downloader=self.name,
                url=url,
                job_type=job_type,
                requested_quality=requested_quality,
                error_type=error_type,
                http_status=http_status,
                reason=str(exc),
            )
            raise DownloadError(error_type=error_type, message=str(exc), http_status=http_status)

        filesize = _extract_filesize(info)
        metadata = MetadataResult(
            url=url,
            title=info.get("title"),
            duration=info.get("duration"),
            filesize=filesize,
            thumbnail_url=info.get("thumbnail"),
            raw_info=info,
        )
        log_with_context(
            logger,
            level=logging.INFO,
            message="Metadata fetched",
            stage="DOWNLOAD",
            downloader=self.name,
            url=url,
            title=metadata.title,
            duration=metadata.duration,
            filesize=metadata.filesize,
        )
        return metadata

    def download(
        self,
        *,
        url: str,
        job_type: JobType,
        requested_quality: str | None,
        target_dir: str,
        cookie_file: str | None = None,
        max_filesize_bytes: int | None = None,
        progress_callback: Callable[[Optional[float], Optional[int], Optional[int], Optional[float]], None]
        | None = None,
    ) -> DownloadResult:
        os.makedirs(target_dir, exist_ok=True)
        metadata = self.fetch_metadata(
            url=url,
            job_type=job_type,
            requested_quality=requested_quality,
            cookie_file=cookie_file,
        )

        if max_filesize_bytes is not None and metadata.filesize is not None:
            if metadata.filesize > max_filesize_bytes:
                raise DownloadError(
                    error_type=ErrorType.SIZE_LIMIT,
                    message=(
                        f"Estimated file size {metadata.filesize} exceeds limit {max_filesize_bytes}"
                    ),
                )

        options = self._base_options(cookie_file=cookie_file, target_dir=target_dir)
        options["format"] = _build_format_selector(job_type, requested_quality)
        if job_type == JobType.AUDIO:
            options["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ]

        if progress_callback is not None:
            options["progress_hooks"] = [
                _build_progress_hook(progress_callback)
            ]

        log_with_context(
            logger,
            level=logging.INFO,
            message="Starting download",
            stage="DOWNLOAD",
            downloader=self.name,
            url=url,
            job_type=job_type,
            requested_quality=requested_quality,
            target_dir=target_dir,
        )

        try:
            with YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=True)
                file_path = ydl.prepare_filename(info)
        except DownloadError:
            raise
        except Exception as exc:  # pragma: no cover - classification handled
            error_type, http_status = _map_error(exc)
            log_with_context(
                logger,
                level=logging.ERROR,
                message="Download failed",
                stage="DOWNLOAD",
                downloader=self.name,
                url=url,
                job_type=job_type,
                requested_quality=requested_quality,
                error_type=error_type,
                http_status=http_status,
                reason=str(exc),
            )
            raise DownloadError(error_type=error_type, message=str(exc), http_status=http_status)

        final_ext = Path(file_path).suffix.lstrip(".")
        filesize = None
        try:
            filesize = int(os.path.getsize(file_path))
        except OSError:
            pass

        if max_filesize_bytes is not None and filesize is not None:
            if filesize > max_filesize_bytes:
                raise DownloadError(
                    error_type=ErrorType.SIZE_LIMIT,
                    message=f"Downloaded file exceeds size limit {max_filesize_bytes}",
                )

        result = DownloadResult(
            url=url,
            file_path=file_path,
            final_ext=final_ext,
            title=info.get("title") or metadata.title,
            thumbnail_url=info.get("thumbnail") or metadata.thumbnail_url,
            filesize=filesize or metadata.filesize,
            metadata=metadata,
        )

        log_with_context(
            logger,
            level=logging.INFO,
            message="Download completed",
            stage="DOWNLOAD",
            downloader=self.name,
            url=url,
            file_path=file_path,
            filesize=result.filesize,
        )
        return result
