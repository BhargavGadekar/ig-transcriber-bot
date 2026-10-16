"""Unit tests for services/video.py."""
import pytest
from pathlib import Path
from services.video import probe_video, generate_video_thumbnail, VideoInfo


@pytest.mark.anyio
async def test_probe_video_fallback(tmp_path: Path):
    dummy_file = tmp_path / "dummy.mp4"
    dummy_file.write_bytes(b"not a real video")

    # When ffprobe fails on dummy bytes, probe_video should gracefully return fallback vertical 720x1280
    info = await probe_video(dummy_file, ffprobe_bin="ffprobe")
    assert isinstance(info, VideoInfo)
    assert info.width == 720
    assert info.height == 1280
    assert not info.has_audio


@pytest.mark.anyio
async def test_generate_video_thumbnail_fallback(tmp_path: Path):
    dummy_file = tmp_path / "dummy.mp4"
    dummy_file.write_bytes(b"not a real video")
    thumb_file = tmp_path / "thumb.jpg"

    # Should gracefully return None when ffmpeg fails on corrupt input
    result = await generate_video_thumbnail(dummy_file, thumb_file)
    assert result is None
