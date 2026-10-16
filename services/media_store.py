"""Persistent media storage, FIFO ring buffer (max 50 videos), midnight IST cleanup, and drive cleaning."""
from __future__ import annotations

import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger("media_store")

# Indian Standard Time (UTC+5:30)
IST_TZ = timezone(timedelta(hours=5, minutes=30))


def save_media_to_archive(
    source_path: Path | str,
    archive_dir: Path | str,
    max_files: int = 50,
) -> Path | None:
    """Save downloaded media to persistent archive folder and enforce FIFO ring buffer."""
    source_path = Path(source_path)
    if not source_path.is_file():
        return None
    archive_dir = Path(archive_dir)
    archive_dir.mkdir(parents=True, exist_ok=True)
    target = archive_dir / source_path.name

    try:
        if source_path.resolve() != target.resolve():
            shutil.copy2(source_path, target)
        log.info("saved media file to archive: %s", target.name)
    except Exception:
        log.exception("could not copy media to archive %s", target)
        return None

    # Enforce FIFO limit: when 51st video arrives, delete oldest 1st one
    enforce_fifo_limit(archive_dir, max_files=max_files)
    return target


def enforce_fifo_limit(archive_dir: Path | str, max_files: int = 50) -> int:
    """Ensure at most `max_files` exist in archive. Older ones are evicted (FIFO)."""
    archive_dir = Path(archive_dir)
    if not archive_dir.is_dir():
        return 0
    files = [
        f for f in archive_dir.iterdir()
        if f.is_file() and not f.name.startswith(".")
    ]
    if len(files) <= max_files:
        return 0

    # Sort oldest first by mtime
    files.sort(key=lambda p: p.stat().st_mtime)
    to_delete = files[: len(files) - max_files]
    deleted = 0
    for f in to_delete:
        try:
            f.unlink()
            deleted += 1
            log.info("FIFO ring buffer evicted oldest file: %s", f.name)
        except OSError:
            log.exception("failed to delete file during FIFO eviction: %s", f)
    return deleted


def clean_drive(archive_dir: Path | str, tmp_dir: Path | str | None = None) -> tuple[int, int]:
    """Purge all archived media and temp files. Returns (deleted_count, freed_bytes)."""
    archive_dir = Path(archive_dir)
    total_deleted = 0
    freed_bytes = 0
    directories = [archive_dir]
    if tmp_dir and Path(tmp_dir).is_dir():
        directories.append(Path(tmp_dir))

    for d in directories:
        if not d.is_dir():
            continue
        for f in list(d.glob("*")):
            if f.is_file() and not f.name.startswith("."):
                try:
                    size = f.stat().st_size
                    f.unlink()
                    total_deleted += 1
                    freed_bytes += size
                except OSError:
                    pass
            elif f.is_dir() and not f.name.startswith("."):
                try:
                    for sub in list(f.glob("*")):
                        if sub.is_file():
                            freed_bytes += sub.stat().st_size
                            sub.unlink()
                            total_deleted += 1
                    shutil.rmtree(f, ignore_errors=True)
                except Exception:
                    pass
    return total_deleted, freed_bytes


def midnight_ist_cleanup(archive_dir: Path | str) -> int:
    """Purge media older than today's midnight in IST (Indian Standard Time)."""
    archive_dir = Path(archive_dir)
    if not archive_dir.is_dir():
        return 0
    now_ist = datetime.now(IST_TZ)
    today_midnight_ist = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff_ts = today_midnight_ist.timestamp()

    deleted = 0
    for f in list(archive_dir.iterdir()):
        if f.is_file() and not f.name.startswith("."):
            try:
                if f.stat().st_mtime < cutoff_ts:
                    f.unlink()
                    deleted += 1
                    log.info("midnight IST cleanup purged old video: %s", f.name)
            except OSError:
                pass
    return deleted
