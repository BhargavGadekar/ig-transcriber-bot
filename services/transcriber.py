"""Local transcription via the whisper.cpp `whisper-cli` binary.

Runs whisper-cli as an asyncio subprocess with Silero VAD enabled, optional
romanized-Hinglish initial prompt, thread count = CPUs-1 and GPU acceleration
whenever the build supports it (Metal/CUDA engage automatically). Output is
requested as SRT + full JSON; the JSON (with per-segment timestamps and the
detected language) is the primary parse target, SRT is a fallback.

Flag names verified against whisper.cpp v1.9.5 (examples/cli/cli.cpp):
  -m model, -f file, -l auto, -t threads, --prompt, --vad, -vm vad-model,
  --max-context N (0 disables carry-over between windows), -osrt, -ojf, -of.
Note: there is NO --no-context flag; context carry-over is disabled with
`--max-context 0`.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from utils.text import Segment, parse_srt

if TYPE_CHECKING:  # pragma: no cover
    from core.config import Settings

log = logging.getLogger(__name__)


class TranscribeFailure(Exception):
    """Transcription failure with a friendly, user-facing message."""

    def __init__(self, kind: str, user_message: str):
        super().__init__(user_message)
        self.kind = kind
        self.user_message = user_message


class _K:
    NO_SPEECH = "no_speech"
    TIMEOUT = "timeout"
    FAILED = "failed"
    BIN_MISSING = "bin_missing"
    CANCELLED = "cancelled"


_MESSAGES = {
    _K.NO_SPEECH: "🤫 No speech detected in this audio.",
    _K.TIMEOUT: "⌛️ Transcription timed out.",
    _K.FAILED: "💥 whisper-cli failed — check the bot logs for details.",
    _K.BIN_MISSING: "🛠 The whisper-cli binary was not found — check WHISPER_BIN.",
    _K.CANCELLED: "🚫 Cancelled.",
}


def _fail(kind: str) -> TranscribeFailure:
    return TranscribeFailure(kind, _MESSAGES[kind])


@dataclass(slots=True)
class WhisperResult:
    language: str | None
    segments: list[Segment]
    text: str
    json_path: Path | None
    srt_path: Path | None


_PROGRESS_RE = re.compile(r"progress\s*=\s*(\d+)%")


def build_command(settings: "Settings", wav_path: Path, out_prefix: Path) -> list[str]:
    """Assemble the whisper-cli argument list from settings."""
    whisper_bin = getattr(settings, "effective_whisper_bin", settings.whisper_bin)
    model_path = getattr(settings, "effective_model_path", settings.whisper_model_path)
    cmd = [
        whisper_bin,
        "-m",
        str(Path(model_path).resolve()),
        "-f",
        str(wav_path),
        "-l",
        "auto",
        "-t",
        str(settings.effective_threads),
    ]
    if settings.whisper_vad:
        cmd.append("--vad")
        vad_model = Path(settings.whisper_vad_model)
        if vad_model.is_file():
            cmd += ["-vm", str(vad_model.resolve())]
        else:
            log.warning(
                "VAD enabled but model %s not found; relying on whisper-cli defaults",
                vad_model,
            )
    # whisper.cpp has no --no-context flag; disabling context carry-over (which
    # can cause repetition loops on music/silence) is done with --max-context 0.
    if settings.whisper_max_context >= 0:
        cmd += ["--max-context", str(settings.whisper_max_context)]
    if getattr(settings, "whisper_no_mmap", False):
        cmd.append("--no-mmap")
    if settings.script_mode == "roman" and settings.roman_prompt.strip():
        cmd += ["--prompt", settings.roman_prompt]
    cmd += ["-osrt", "-ojf", "-of", str(out_prefix)]
    if settings.whisper_extra_args.strip():
        cmd += shlex.split(settings.whisper_extra_args)
    return cmd


async def transcribe(
    wav_path: Path,
    out_prefix: Path,
    *,
    settings: "Settings",
    audio_duration_s: float | None = None,
    register: Callable[[asyncio.subprocess.Process], None] | None = None,
    progress: Callable[[int], None] | None = None,
) -> WhisperResult:
    """Run whisper-cli on a 16 kHz mono WAV and return parsed segments."""
    cmd = build_command(settings, Path(wav_path), Path(out_prefix))
    log.info("whisper-cli: %s", " ".join(shlex.quote(c) for c in cmd))
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        raise _fail(_K.BIN_MISSING) from exc
    if register is not None:
        register(proc)

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    async def pump(stream: asyncio.StreamReader, sink: list[str]) -> None:
        while True:
            raw = await stream.readline()
            if not raw:
                break
            line = raw.decode(errors="replace")
            sink.append(line)
            if progress is not None:
                match = _PROGRESS_RE.search(line)
                if match:
                    try:
                        progress(int(match.group(1)))
                    except Exception:  # noqa: BLE001 - progress must never kill a job
                        pass

    pumps = [
        asyncio.create_task(pump(proc.stdout, stdout_lines)),
        asyncio.create_task(pump(proc.stderr, stderr_lines)),
    ]
    timeout = settings.whisper_timeout_base + int(
        (audio_duration_s or 0) * settings.whisper_timeout_per_second
    )
    try:
        await asyncio.wait_for(proc.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        await asyncio.gather(*pumps, return_exceptions=True)
        log.error("whisper-cli timed out after %ss (audio %.0fs)", timeout, audio_duration_s or 0)
        raise _fail(_K.TIMEOUT) from None
    await asyncio.gather(*pumps, return_exceptions=True)

    if proc.returncode is not None and proc.returncode < 0:
        # Terminated by SIGTERM/SIGKILL → job was cancelled.
        raise _fail(_K.CANCELLED)
    if proc.returncode != 0:
        tail = "".join(stderr_lines[-8:] + stdout_lines[-8:])[-800:]
        log.error(
            "whisper-cli exited with %s; output tail:\n%s", proc.returncode, tail
        )
        raise _fail(_K.FAILED)

    json_path = Path(str(out_prefix) + ".json")
    srt_path = Path(str(out_prefix) + ".srt")
    segments: list[Segment] = []
    language: str | None = None
    text = ""
    if json_path.is_file():
        try:
            data = json.loads(json_path.read_text(encoding="utf-8", errors="replace"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("failed to parse whisper JSON output: %s", exc)
            data = {}
        # whisper.cpp JSON layout (v1.9.x): {"result": {"language": "en"},
        # "transcription": [{"timestamps": {...}, "offsets": {"from": <ms>,
        # "to": <ms>}, "text": " ..."}, ...]}
        language = data.get("language") or (data.get("result") or {}).get("language")
        raw_items = data.get("transcription") or data.get("segments") or []
        for item in raw_items:
            if "offsets" in item:
                # whisper.cpp format: offsets.from/to are milliseconds
                start = float(item["offsets"].get("from", 0)) / 1000.0
                end = float(item["offsets"].get("to", 0)) / 1000.0
            else:
                start = float(item.get("start", 0.0))
                end = float(item.get("end", 0.0))
            segments.append(Segment(start, end, str(item.get("text", ""))))
        text = " ".join(seg.text for seg in segments)
    elif srt_path.is_file():
        segments = parse_srt(srt_path.read_text(encoding="utf-8", errors="replace"))
        text = " ".join(seg.text for seg in segments)

    if not segments:
        if settings.whisper_vad:
            log.info("VAD detected no speech; retrying once without VAD fallback...")
            no_vad_settings = settings.model_copy(update={"whisper_vad": False})
            return await transcribe(
                wav_path,
                out_prefix,
                settings=no_vad_settings,
                audio_duration_s=audio_duration_s,
                register=register,
                progress=progress,
            )
        raise _fail(_K.NO_SPEECH)

    return WhisperResult(
        language=(language or None),
        segments=segments,
        text=text.strip(),
        json_path=json_path if json_path.is_file() else None,
        srt_path=srt_path if srt_path.is_file() else None,
    )
