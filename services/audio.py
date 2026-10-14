"""Audio extraction with ffmpeg: 16 kHz mono pcm_s16le WAV for whisper.cpp."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)


class AudioError(Exception):
    """Raised when audio extraction or probing fails."""


async def extract_audio_wav(
    source: Path | str,
    target: Path | str,
    *,
    ffmpeg_bin: str = "ffmpeg",
    register: Callable[[asyncio.subprocess.Process], None] | None = None,
) -> None:
    """Extract audio from ``source`` into a whisper-ready WAV (16 kHz, mono,
    pcm_s16le). ``register`` exposes the process handle so a running job can be
    terminated on /cancel."""
    cmd = [
        ffmpeg_bin,
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-i",
        str(source),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(target),
    ]
    log.debug("ffmpeg: %s", " ".join(cmd))
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise AudioError(f"ffmpeg binary not found at '{ffmpeg_bin}'") from exc
    if register is not None:
        register(proc)
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        tail = stderr.decode(errors="replace")[-600:]
        raise AudioError(f"ffmpeg failed (exit {proc.returncode}): {tail}")


async def probe_duration_seconds(
    path: Path | str, *, ffprobe_bin: str = "ffprobe"
) -> float | None:
    """Return media duration in seconds via ffprobe, or None if unavailable."""
    cmd = [
        ffprobe_bin,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return None
    stdout, _ = await proc.communicate()
    if proc.returncode != 0:
        return None
    try:
        return float(stdout.decode().strip())
    except ValueError:
        return None
