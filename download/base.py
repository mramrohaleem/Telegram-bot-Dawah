from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

from storage.models import ErrorType, JobType


class DownloadError(Exception):
    """Represents a failure during metadata fetch or download."""

    def __init__(self, error_type: ErrorType, message: str, *, http_status: Optional[int] = None):
        super().__init__(message)
        self.error_type = error_type
        self.http_status = http_status


@dataclass
class MetadataResult:
    url: str
    title: Optional[str]
    duration: Optional[float]
    filesize: Optional[int]
    thumbnail_url: Optional[str]
    raw_info: dict[str, Any]


@dataclass
class DownloadResult:
    url: str
    file_path: str
    final_ext: str
    title: Optional[str]
    thumbnail_url: Optional[str]
    filesize: Optional[int]
    metadata: MetadataResult


class BaseDownloader(ABC):
    @abstractmethod
    def fetch_metadata(
        self,
        *,
        url: str,
        job_type: JobType,
        requested_quality: str | None,
        cookie_file: str | None = None,
    ) -> MetadataResult:
        ...

    @abstractmethod
    def download(
        self,
        *,
        url: str,
        job_type: JobType,
        requested_quality: str | None,
        target_dir: str,
        cookie_file: str | None = None,
        max_filesize_bytes: int | None = None,
    ) -> DownloadResult:
        ...
