"""Unit tests for services/media_store.py."""
import time
from pathlib import Path
from services.media_store import (
    clean_drive,
    enforce_fifo_limit,
    midnight_ist_cleanup,
    save_media_to_archive,
)


def test_save_and_fifo_eviction(tmp_path: Path):
    archive_dir = tmp_path / "downloads"
    archive_dir.mkdir()

    # Create dummy source files
    created_targets = []
    for i in range(5):
        src = tmp_path / f"video_{i}.mp4"
        src.write_text(f"dummy content {i}")
        time.sleep(0.01)  # ensure distinct mtimes
        target = save_media_to_archive(src, archive_dir, max_files=3)
        assert target is not None
        assert target.exists()
        created_targets.append(target)

    # Max files is 3, so only 3 should remain
    remaining = sorted(list(archive_dir.glob("*.mp4")))
    assert len(remaining) == 3
    # video_0 and video_1 should have been evicted
    assert not (archive_dir / "video_0.mp4").exists()
    assert not (archive_dir / "video_1.mp4").exists()
    assert (archive_dir / "video_2.mp4").exists()
    assert (archive_dir / "video_3.mp4").exists()
    assert (archive_dir / "video_4.mp4").exists()


def test_clean_drive(tmp_path: Path):
    archive_dir = tmp_path / "downloads"
    archive_dir.mkdir()
    tmp_dir = tmp_path / "tmp"
    tmp_dir.mkdir()

    f1 = archive_dir / "v1.mp4"
    f1.write_bytes(b"12345")
    f2 = tmp_dir / "t1.wav"
    f2.write_bytes(b"67890")

    deleted, freed = clean_drive(archive_dir, tmp_dir)
    assert deleted == 2
    assert freed == 10
    assert not f1.exists()
    assert not f2.exists()


def test_midnight_ist_cleanup(tmp_path: Path):
    archive_dir = tmp_path / "downloads"
    archive_dir.mkdir()

    old_file = archive_dir / "old_video.mp4"
    old_file.write_text("old")
    # Set mtime to 2 days ago
    import os
    two_days_ago = time.time() - (2 * 86400)
    os.utime(old_file, (two_days_ago, two_days_ago))

    new_file = archive_dir / "new_video.mp4"
    new_file.write_text("new")

    deleted = midnight_ist_cleanup(archive_dir)
    assert deleted == 1
    assert not old_file.exists()
    assert new_file.exists()
