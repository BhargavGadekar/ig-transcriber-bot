"""Video probing (dimensions, duration, aspect ratio) and thumbnail generation.

Ensures Telegram renders videos with proper 9:16 aspect ratio preview and natural thumbnail
instead of a blacked-out square placeholder.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("video")


@dataclass(slots=True)
class VideoInfo:
    width: int
    height: int
    duration_s: int
    has_audio: bool
    codec: str


async def probe_video(
    path: Path | str,
    *,
    ffprobe_bin: str = "ffprobe",
) -> VideoInfo:
    """Inspect video with ffprobe to determine width, height, duration, and audio presence."""
    path = Path(path)
    cmd = [
        ffprobe_bin,
        "-v",
        "error",
        "-show_entries",
        "stream=width,height,duration,codec_name,codec_type:format=duration",
        "-of",
        "json",
        str(path),
    ]
    width, height, duration = 0, 0, 0
    has_audio = False
    codec = "h264"
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode == 0:
            data = json.loads(stdout.decode())
            streams = data.get("streams") or []
            format_info = data.get("format") or {}
            duration_val = format_info.get("duration")
            if duration_val:
                try:
                    duration = int(float(duration_val))
                except ValueError:
                    pass
            for s in streams:
                if s.get("codec_type") == "video" and not width:
                    width = int(s.get("width") or 0)
                    height = int(s.get("height") or 0)
                    codec = str(s.get("codec_name") or "h264")
                    if not duration and s.get("duration"):
                        try:
                            duration = int(float(s["duration"]))
                        except ValueError:
                            pass
                elif s.get("codec_type") == "audio":
                    has_audio = True
    except Exception:
        log.exception("error probing video %s", path)

    # Fallback to standard vertical reel dimensions if unprobed
    if not width or not height:
        width, height = 720, 1280
    return VideoInfo(
        width=width,
        height=height,
        duration_s=duration,
        has_audio=has_audio,
        codec=codec,
    )


async def generate_video_thumbnail(
    video_path: Path | str,
    thumb_path: Path | str,
    *,
    ffmpeg_bin: str = "ffmpeg",
    at_second: float = 1.0,
) -> Path | None:
    """Generate a high-quality JPEG thumbnail frame from the video using ffmpeg."""
    video_path = Path(video_path)
    thumb_path = Path(thumb_path)
    thumb_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_bin,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        str(at_second),
        "-i",
        str(video_path),
        "-vframes",
        "1",
        "-q:v",
        "2",
        str(thumb_path),
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.communicate()
        if thumb_path.is_file() and thumb_path.stat().st_size > 0:
            return thumb_path
    except Exception:
        log.warning("failed to generate video thumbnail for %s", video_path)
    return None
