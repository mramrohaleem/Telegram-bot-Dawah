"""Helpers to determine the source type of a URL based on its domain."""
from __future__ import annotations

from storage.models import SourceType

YOUTUBE_DOMAINS = {"youtube.com", "www.youtube.com", "youtu.be"}
FACEBOOK_DOMAINS = {"facebook.com", "www.facebook.com", "fb.watch"}
ARCHIVE_DOMAINS = {"archive.org", "www.archive.org"}
TARIQ_ALLAH_DOMAINS = {
    "way2allah.com",
    "www.way2allah.com",
    "islamway.net",
    "www.islamway.net",
}


def detect_source_type(domain: str) -> SourceType | None:
    """Map a domain to a SourceType if supported."""

    normalized = domain.lower()

    if normalized in YOUTUBE_DOMAINS:
        return SourceType.YOUTUBE
    if normalized in FACEBOOK_DOMAINS:
        return SourceType.FACEBOOK
    if normalized in ARCHIVE_DOMAINS:
        return SourceType.ARCHIVE
    if normalized in TARIQ_ALLAH_DOMAINS:
        return SourceType.TARIQ_ALLAH

    return None
