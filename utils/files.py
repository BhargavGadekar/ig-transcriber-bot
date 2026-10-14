"""Filesystem helpers: filename sanitizing, per-job temp dirs, cleanup."""
from __future__ import annotations

import hashlib
import re
import shutil
import tempfile
import unicodedata
from pathlib import Path

# Characters forbidden in Obsidian/Windows/macOS filenames.
_FORBIDDEN = re.compile(r'[\\/*?:"<>|#\[\]^]')


def sanitize_filename_part(value: str | None, *, max_len: int = 40, fallback: str = "instagram") -> str:
    """Sanitize a string for use inside a filename.

    Unicode letters/digits are preserved (Hindi/Devanagari titles are fine in
    Obsidian); filesystem-hostile characters are replaced, whitespace collapses
    to single underscores and the result is truncated to ``max_len``.
    """
    value = unicodedata.normalize("NFKC", str(value or ""))
    value = _FORBIDDEN.sub(" ", value)
    value = re.sub(r"[\s_]+", "_", value).strip("_.-")
    if len(value) > max_len:
        value = value[:max_len].rstrip("_.-")
    return value or fallback


def short_id(seed: str, *, length: int = 8) -> str:
    """Stable short hex id derived from a seed string (e.g. a canonical URL)."""
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:length]


def make_job_dir(base_dir: Path | str) -> Path:
    """Create a unique per-job temp directory under ``base_dir``."""
    base = Path(base_dir)
    base.mkdir(parents=True, exist_ok=True)
    job_dir = Path(tempfile.mkdtemp(prefix="job_", dir=str(base)))
    return job_dir


def remove_tree(path: Path | str | None) -> None:
    """Best-effort recursive delete; never raises."""
    if path is None:
        return
    shutil.rmtree(path, ignore_errors=True)


def clean_dir_contents(dir_path: Path | str) -> None:
    """Delete everything inside ``dir_path`` (used for tmp cleanup at startup)."""
    path = Path(dir_path)
    if not path.exists():
        return
    for child in path.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child, ignore_errors=True)
        else:
            try:
                child.unlink()
            except OSError:
                pass
