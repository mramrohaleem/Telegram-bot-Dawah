"""Utilities for extracting, normalizing, and validating URLs."""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlparse, urlunparse

ALLOWED_SCHEMES = {"https", "http"}


class InvalidUrlError(ValueError):
    """Raised when a URL is missing, malformed, or uses an unsupported scheme."""


def extract_first_url_from_text(text: str) -> Optional[str]:
    """Extract the first URL-like token from a text message.

    This uses a simple regex to pick out the first occurrence of an HTTP(S) URL.
    The goal is robustness for typical Telegram messages, not perfect URL parsing.
    """

    if not text:
        return None

    match = re.search(r"(https?://[^\s]+)", text)
    if match:
        return match.group(1)
    return None


def normalize_url(url: str) -> str:
    """Normalize a URL for deduplication and comparison."""

    trimmed = url.strip()
    parsed = urlparse(trimmed)
    normalized = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
    )
    return urlunparse(normalized)


def validate_url(url: str) -> str:
    """Validate URL structure and allowed scheme, returning a normalized string."""

    if not url:
        raise InvalidUrlError("URL is missing")

    normalized = normalize_url(url)
    parsed = urlparse(normalized)

    if parsed.scheme not in ALLOWED_SCHEMES:
        raise InvalidUrlError(f"Unsupported URL scheme: {parsed.scheme}")

    if not parsed.netloc:
        raise InvalidUrlError("URL must include a hostname")

    return normalized


def get_url_domain(url: str) -> str:
    """Return the normalized domain (host) portion of a URL."""

    parsed = urlparse(normalize_url(url))
    return parsed.netloc
