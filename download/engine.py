from __future__ import annotations

from typing import Optional

from download.base import BaseDownloader, DownloadError, DownloadResult
from download.youtube import YouTubeDownloader
from storage.models import ErrorType, JobType, SourceType


class DownloadEngine:
    """Dispatch downloads to source-specific downloaders."""

    def __init__(self) -> None:
        self._youtube = YouTubeDownloader()

    def get_downloader(self, source_type: SourceType) -> BaseDownloader:
        if source_type == SourceType.YOUTUBE:
            return self._youtube

        raise DownloadError(
            error_type=ErrorType.UNSUPPORTED_SOURCE,
            message=f"No downloader implemented for source type {source_type}",
        )

    def download_job(
        self,
        *,
        source_type: SourceType,
        url: str,
        job_type: JobType,
        requested_quality: str | None,
        target_dir: str,
        cookie_file: Optional[str] = None,
        max_filesize_bytes: Optional[int] = None,
    ) -> DownloadResult:
        downloader = self.get_downloader(source_type)
        return downloader.download(
            url=url,
            job_type=job_type,
            requested_quality=requested_quality,
            target_dir=target_dir,
            cookie_file=cookie_file,
            max_filesize_bytes=max_filesize_bytes,
        )
