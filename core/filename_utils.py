from __future__ import annotations

import re
from pathlib import Path


def sanitize_title_to_filename(title: str, ext: str | None = None) -> str:
    """Return a filesystem-safe filename derived from a title."""

    safe = re.sub(r"[\\/:*?\"<>|]", "_", title)
    safe = safe.replace("..", "_")
    safe = safe.strip().strip(".")
    if not safe:
        safe = "media"
    if len(safe) > 120:
        safe = safe[:120]

    if ext:
        suffix = ext.lstrip(".")
        return f"{safe}.{suffix}"
    return safe


def derive_filename_from_path(path: str) -> str:
    return Path(path).name
