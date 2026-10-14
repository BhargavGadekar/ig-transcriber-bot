"""Job pipeline orchestration.

Flow: message handler → JobManager.submit() → download stage (parallel,
semaphore-limited) → transcription queue → single (configurable) CPU worker →
extract audio (ffmpeg) → transcribe (whisper-cli) → render Markdown → deliver
to Telegram → cache transcript in SQLite.

Temp files are always cleaned up, including on failure and cancellation.
"""
from __future__ import annotations

import asyncio
import re
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from bot.progress import send_with_flood_retry
from services.audio import AudioError, extract_audio_wav, probe_duration_seconds
from services.downloader import DownloadFailure, download_video
from services.markdown import VideoMeta, build_md_filename, render_markdown
from services.summarizer import Summarizer
from services.transcriber import TranscribeFailure, transcribe
from utils.files import make_job_dir, remove_tree
from utils.languages import language_name
from utils.text import (
    Segment,
    build_paragraphs,
    clean_segments,
    format_timestamp,
    render_transcript,
    word_count,
)
from utils.urls import normalize_instagram_url

if TYPE_CHECKING:  # pragma: no cover
    from pyrogram.client import Client

    from core.config import Settings
    from core.database import Database

log = logging.getLogger(__name__)

_ACTIVE_STATES = ("extracting", "transcribing", "summarizing")
_CANCELABLE_STATES = ("queued", "downloading", "waiting", "extracting", "transcribing", "summarizing")


class JobCancelled(Exception):
    """Raised internally when a job was cancelled via /cancel."""


class ProgressReporter(Protocol):
    """Interface the bot layer provides for editing a job's status message."""

    def update(self, text: str) -> None: ...

    def update_threadsafe(self, text: str) -> None: ...

    async def finalize(self, text: str) -> None: ...

    async def fail(self, text: str) -> None: ...


@dataclass(slots=True)
class Job:
    db_id: int
    user_id: int
    chat_id: int
    url: str
    reporter: ProgressReporter | None = None
    state: str = "queued"
    tmp_dir: Path | None = None
    download_result: Any = None
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    subprocs: set = field(default_factory=set)
    created_at: float = field(default_factory=time.monotonic)

    def throw_if_cancelled(self) -> None:
        if self.cancel_event.is_set():
            raise JobCancelled()

    def register_proc(self, proc) -> None:
        self.subprocs.add(proc)

    def interrupt(self) -> None:
        """Request cancellation and terminate any tracked subprocesses."""
        self.cancel_event.set()
        for proc in list(self.subprocs):
            try:
                proc.terminate()
            except ProcessLookupError:
                pass


class JobManager:
    """Owns the download semaphore, transcription queue and worker tasks."""

    def __init__(self, settings: "Settings", db: "Database", client: "Client"):
        self._settings = settings
        self._db = db
        self._client = client
        self._download_sem = asyncio.Semaphore(max(1, settings.download_concurrency))
        self._queue: asyncio.Queue[Job | None] = asyncio.Queue(maxsize=max(10, settings.queue_max_size))
        self._workers: list[asyncio.Task] = []
        self._stage_tasks: set[asyncio.Task] = set()
        self._jobs: dict[int, Job] = {}
        self._started_at = time.monotonic()
        self._summarizer = Summarizer(settings)
        self.counters = {"done": 0, "failed": 0, "cached": 0, "cancelled": 0}

    # --- lifecycle ------------------------------------------------------------

    async def start(self) -> None:
        for i in range(max(1, self._settings.worker_concurrency)):
            self._workers.append(
                asyncio.create_task(self._worker(i), name=f"whisper-worker-{i}")
            )

    async def stop(self, timeout: float = 10.0) -> None:
        for _ in self._workers:
            self._queue.put_nowait(None)
        if self._workers:
            try:
                await asyncio.wait_for(asyncio.gather(*self._workers), timeout=timeout)
            except asyncio.TimeoutError:
                log.warning("workers did not stop within %.0fs; cancelling", timeout)
                for task in self._workers:
                    task.cancel()
        for task in list(self._stage_tasks):
            task.cancel()
        for job in list(self._jobs.values()):
            job.interrupt()
            self._cleanup(job)
        self._jobs.clear()

    # --- submission & introspection ---------------------------------------------

    def submit(self, job: Job) -> bool:
        if len(self._jobs) >= self._settings.queue_max_size:
            asyncio.create_task(
                self._fail(job, f"⏳ Server queue is currently full ({self._settings.queue_max_size} jobs). Please try again shortly.")
            )
            return False
        self._jobs[job.db_id] = job
        task = asyncio.create_task(
            self._download_stage(job), name=f"job-{job.db_id}-download"
        )
        self._stage_tasks.add(task)
        task.add_done_callback(self._stage_tasks.discard)
        return True

    def stats(self) -> dict:
        active = sum(1 for j in self._jobs.values() if j.state in _ACTIVE_STATES)
        return {
            "uptime_s": round(time.monotonic() - self._started_at, 1),
            "queue_waiting": self._queue.qsize(),
            "queue_capacity": self._settings.queue_max_size,
            "active_transcriptions": active,
            "total_tracked_jobs": len(self._jobs),
            "workers": len(self._workers),
            **{f"jobs_{key}": value for key, value in self.counters.items()},
            "llm": self._summarizer.stats() if self._summarizer else {"configured": False},
        }

    async def cancel_user_jobs(self, user_id: int) -> dict[str, int]:
        counts = {"queued": 0, "active": 0}
        for job in list(self._jobs.values()):
            if job.user_id != user_id or job.state not in _CANCELABLE_STATES:
                continue
            was_active = job.state in _ACTIVE_STATES
            job.interrupt()
            counts["active" if was_active else "queued"] += 1
        return counts

    # --- download stage (parallel) ------------------------------------------------

    async def _download_stage(self, job: Job) -> None:
        try:
            job.throw_if_cancelled()
            job.state = "queued"
            await self._db.update_job(job.db_id, status="queued")
            if job.reporter:
                q_pos = sum(1 for j in self._jobs.values() if j.state in ("queued", "downloading"))
                if q_pos > 1:
                    job.reporter.update(f"⏳ In download queue (#{q_pos})…")
                else:
                    job.reporter.update("⬇️ Preparing download…")

            def progress(pct: int) -> None:
                if job.reporter:
                    job.reporter.update_threadsafe(f"⬇️ Downloading… {pct}%")

            async with self._download_sem:
                job.throw_if_cancelled()
                if job.tmp_dir is None:
                    job.tmp_dir = make_job_dir(self._settings.tmp_dir)
                job.state = "downloading"
                await self._db.update_job(job.db_id, status="downloading")
                if job.reporter:
                    job.reporter.update("⬇️ Downloading…")

                job.download_result = await download_video(
                    job.url,
                    job.tmp_dir,
                    settings=self._settings,
                    progress=progress if job.reporter else None,
                )
            job.throw_if_cancelled()
            job.state = "waiting"
            q_wait = self._queue.qsize() + 1
            if job.reporter:
                if q_wait > 1:
                    job.reporter.update(
                        f"⏳ Queued for transcription (#{q_wait} in line)…"
                    )
                else:
                    job.reporter.update("⏳ Queued for transcription…")
            await self._db.update_job(job.db_id, status="waiting")
            await self._queue.put(job)
        except (DownloadFailure, TranscribeFailure, AudioError) as exc:
            if job.cancel_event.is_set():
                await self._cancelled(job)  # subprocess killed by /cancel, not a real failure
            else:
                await self._fail(job, str(exc), exc)
        except JobCancelled:
            await self._cancelled(job)
        except asyncio.CancelledError:
            self._cleanup(job)
            self._jobs.pop(job.db_id, None)
            raise
        except Exception as exc:
            log.exception("job %s: unexpected download-stage failure", job.db_id)
            await self._fail(job, "💥 Unexpected error while downloading — see logs.", exc)

    # --- transcription workers --------------------------------------------------

    async def _worker(self, index: int) -> None:
        while True:
            job = await self._queue.get()
            try:
                if job is None:
                    break
                await self._process(job)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("worker %d: unhandled error", index)
            finally:
                self._queue.task_done()

    async def _process(self, job: Job) -> None:
        try:
            job.throw_if_cancelled()
            downloaded = job.download_result
            if downloaded is None:  # defensive: download stage lost the file
                raise DownloadFailure("no_video", "🚫 Download result missing.")

            job.state = "extracting"
            await self._db.update_job(job.db_id, status="extracting")
            if job.reporter:
                job.reporter.update("🎧 Extracting audio…")

            duration_s = int(downloaded.duration_s or 0)
            if not duration_s:
                probed = await probe_duration_seconds(
                    downloaded.filepath, ffprobe_bin=self._settings.ffprobe_bin
                )
                duration_s = int(probed) if probed else 0
            if duration_s and duration_s > self._settings.max_duration_seconds:
                raise DownloadFailure(
                    "too_long",
                    f"⏱ Video is too long ({format_timestamp(duration_s)} — limit is "
                    f"{format_timestamp(self._settings.max_duration_seconds)}).",
                )

            wav_path = job.tmp_dir / "audio.wav"
            await extract_audio_wav(
                downloaded.filepath,
                wav_path,
                ffmpeg_bin=self._settings.ffmpeg_bin,
                register=job.register_proc,
            )

            job.throw_if_cancelled()
            job.state = "transcribing"
            await self._db.update_job(job.db_id, status="transcribing")
            if job.reporter:
                job.reporter.update("✍️ Transcribing…")

            user_settings = await self._db.get_user_settings(job.user_id) or {}
            script_mode = user_settings.get("script_mode") or self._settings.script_mode
            effective_settings = (
                self._settings.model_copy(update={"script_mode": script_mode})
                if script_mode != self._settings.script_mode
                else self._settings
            )

            def whisper_progress(pct: int) -> None:
                if job.reporter:
                    job.reporter.update(f"✍️ Transcribing… {pct}%")

            result = await transcribe(
                wav_path,
                job.tmp_dir / "transcript",
                settings=effective_settings,
                audio_duration_s=duration_s or None,
                register=job.register_proc,
                progress=whisper_progress if job.reporter else None,
            )
            job.throw_if_cancelled()

            to_roman = (script_mode == "roman")
            segments = clean_segments(
                result.segments,
                keep_tags=self._settings.transcript_keep_tags,
                to_roman=to_roman,
            )
            if not segments:
                raise TranscribeFailure("no_speech", "🤫 No speech detected in this audio.")

            language = (result.language or "").strip().lower() or "und"
            if to_roman and language in ("ur", "hi", "und"):
                language = "hinglish"
            meta = VideoMeta(
                url=job.url,
                author=downloaded.author,
                title=downloaded.title,
                upload_date=downloaded.upload_date,
                duration_s=duration_s or None,
                caption=downloaded.caption,
                language=language,
                model_name=self._settings.whisper_model_name,
            )

            # Optional AI Summarization (Obsidian summary, claims, facts)
            if self._summarizer and self._summarizer.is_configured:
                job.throw_if_cancelled()
                job.state = "summarizing"
                await self._db.update_job(job.db_id, status="summarizing")
                if job.reporter:
                    job.reporter.update("🧠 Generating AI summary…")
                raw_text = "\n\n".join(s.text for s in segments)
                summary_text = await self._summarizer.summarize(meta, raw_text)
                if summary_text:
                    meta.summary = summary_text
            # Cache under both the requested URL and the canonical page URL
            # (share links resolve to a different canonical form).
            canonical = normalize_instagram_url(downloaded.webpage_url) or job.url
            segment_dicts = [
                {"start": s.start, "end": s.end, "text": s.text} for s in segments
            ]
            for key in {job.url, canonical}:
                try:
                    await self._db.put_transcript(key, meta.to_dict(), segment_dicts)
                except Exception:
                    log.exception("failed to cache transcript under %s", key)

            await self._render_and_deliver(job, meta, segments, user_settings)

            job.state = "done"
            self.counters["done"] += 1
            await self._db.update_job(
                job.db_id, status="done", md_filename=build_md_filename(meta)
            )
        except (DownloadFailure, TranscribeFailure, AudioError) as exc:
            if job.cancel_event.is_set():
                await self._cancelled(job)  # subprocess killed by /cancel, not a real failure
            else:
                await self._fail(job, str(exc), exc)
        except JobCancelled:
            await self._cancelled(job)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("job %s: unexpected pipeline failure", job.db_id)
            await self._fail(job, "💥 Unexpected error — see logs.", exc)
        finally:
            self._cleanup(job)
            self._jobs.pop(job.db_id, None)

    # --- rendering & delivery -----------------------------------------------------

    def _render(
        self,
        meta: VideoMeta,
        segments: list[Segment],
        user_settings: dict[str, Any],
    ) -> tuple[str, str, int]:
        timestamps = user_settings.get("timestamps")
        if timestamps is None:
            timestamps = self._settings.timestamps
        paragraphs = build_paragraphs(segments)
        transcript_text = render_transcript(
            paragraphs,
            with_timestamps=bool(timestamps),
            interval_s=max(10, self._settings.timestamp_interval_seconds),
        )
        md_text = render_markdown(meta, transcript_text, summary_markdown=meta.summary)
        words = word_count("\n\n".join(p.text for p in paragraphs))
        return md_text, transcript_text, words

    async def _render_and_deliver(
        self,
        job: Job,
        meta: VideoMeta,
        segments: list[Segment],
        user_settings: dict[str, Any],
    ) -> None:
        md_text, transcript_text, words = self._render(meta, segments, user_settings)
        filename = build_md_filename(meta)
        assert job.tmp_dir is not None
        md_path = job.tmp_dir / filename

        def write_files() -> None:
            md_path.write_text(md_text, encoding="utf-8")
            if self._settings.md_output_dir:
                try:
                    (Path(self._settings.md_output_dir) / filename).write_text(
                        md_text, encoding="utf-8"
                    )
                except OSError:
                    log.exception("could not save markdown copy to MD_OUTPUT_DIR")

        await asyncio.to_thread(write_files)

        lang_name = language_name(meta.language)
        lang_label = (
            lang_name
            if lang_name.lower() == meta.language.lower()
            else f"{lang_name} ({meta.language})"
        )
        summary = (
            f"✅ Done — {lang_label} • "
            f"⏱ {format_timestamp(meta.duration_s or 0)} • {words} words"
        )
        if job.reporter:
            await job.reporter.finalize(f"{summary}\n📄 {filename}")

        if job.download_result and getattr(job.download_result, "filepath", None):
            await self._send_media(job.chat_id, job.download_result.filepath, meta)

        if meta.summary:
            callout = self._extract_summary_callout(meta.summary)
            if callout:
                await self._send_text(
                    job.chat_id, f"💡 *Executive Summary:*\n\n{callout}"[:4000]
                )

        if len(transcript_text) <= self._settings.preview_max_chars:
            await self._send_text(
                job.chat_id, f"📝 Preview:\n\n{transcript_text}"[:4000]
            )
        await self._send_document(
            job.chat_id, md_path, filename, caption=(meta.title[:180] or None)
        )

    async def serve_cached(
        self, job: Job, meta_dict: dict, segment_dicts: list[dict]
    ) -> None:
        """Re-render and instantly send a cached transcript (no re-transcription)."""
        tmp_dir: Path | None = None
        try:
            meta = VideoMeta.from_dict(meta_dict)
            segments = [Segment(**item) for item in segment_dicts]
            user_settings = await self._db.get_user_settings(job.user_id) or {}
            md_text, transcript_text, words = self._render(meta, segments, user_settings)
            filename = build_md_filename(meta)
            tmp_dir = make_job_dir(self._settings.tmp_dir)
            md_path = tmp_dir / filename
            await asyncio.to_thread(md_path.write_text, md_text, "utf-8")

            lang_name = language_name(meta.language)
            lang_label = (
                lang_name
                if lang_name.lower() == meta.language.lower()
                else f"{lang_name} ({meta.language})"
            )
            summary = (
                f"⚡ Cached — {lang_label} • "
                f"⏱ {format_timestamp(meta.duration_s or 0)} • {words} words"
            )
            if len(transcript_text) <= self._settings.preview_max_chars:
                await self._send_text(
                job.chat_id, f"📝 Preview:\n\n{transcript_text}"[:4000]
                )
            await self._send_document(
                job.chat_id, md_path, filename, caption=(meta.title[:180] or None)
            )
            await self._send_text(job.chat_id, summary)
            self.counters["cached"] += 1
        except Exception as exc:
            log.exception("job %s: failed to serve cached transcript", job.db_id)
            await self._send_text(
                job.chat_id, "💥 Failed to send the cached transcript — see logs."
            )
            raise exc
        finally:
            remove_tree(tmp_dir)

    async def _send_text(self, chat_id: int, text: str) -> None:
        await send_with_flood_retry(
            lambda: self._client.send_message(
                chat_id, text, disable_web_page_preview=True
            )
        )

    @staticmethod
    def _extract_summary_callout(summary_md: str) -> str:
        lines: list[str] = []
        for line in summary_md.splitlines():
            s = line.strip()
            if s.startswith(">"):
                cleaned = s.lstrip(">").strip()
                if cleaned.startswith("[!summary]"):
                    cleaned = cleaned[len("[!summary]"):].strip()
                if cleaned.lower().startswith("executive summary"):
                    cleaned = cleaned[len("executive summary"):].strip(" -:")
                if cleaned:
                    lines.append(cleaned)
            elif lines and not s.startswith("#") and s:
                lines.append(s)
            elif lines and (s.startswith("#") or not s):
                break
        return "\n".join(lines).strip()

    async def _send_media(
        self, chat_id: int, path: Path, meta: VideoMeta
    ) -> None:
        if not path or not path.exists():
            return
        caption = (meta.title[:180] or None) if meta.title else None
        suffix = path.suffix.lower()
        try:
            if suffix in (".mp4", ".mov", ".mkv", ".webm", ".m4v"):
                duration = int(meta.duration_s or 0) or None
                await send_with_flood_retry(
                    lambda: self._client.send_video(
                        chat_id,
                        video=str(path),
                        caption=caption,
                        duration=duration,
                        supports_streaming=True,
                    )
                )
            elif suffix in (".mp3", ".m4a", ".wav", ".aac", ".ogg", ".opus"):
                await send_with_flood_retry(
                    lambda: self._client.send_audio(
                        chat_id,
                        audio=str(path),
                        caption=caption,
                        duration=int(meta.duration_s or 0) or None,
                    )
                )
            else:
                await send_with_flood_retry(
                    lambda: self._client.send_document(
                        chat_id,
                        document=str(path),
                        caption=caption,
                    )
                )
        except Exception:
            log.warning("failed to deliver downloaded media %s", path, exc_info=True)

    async def _send_document(
        self, chat_id: int, path: Path, filename: str, caption: str | None = None
    ) -> None:
        try:
            await send_with_flood_retry(
                lambda: self._client.send_document(
                    chat_id, document=str(path), file_name=filename, caption=caption
                )
            )
        except Exception as exc:
            log.exception("failed to deliver document %s", filename)
            raise RuntimeError(
                "📤 Couldn't deliver the file to Telegram (it may be cached — "
                "send the link again in a moment)."
            ) from exc

    # --- failure / cancellation ---------------------------------------------------

    async def _fail(self, job: Job, message: str, exc: BaseException | None = None) -> None:
        self.counters["failed"] += 1
        if exc is not None:
            log.error(
                "job %s failed (%s): %s",
                job.db_id,
                type(exc).__name__,
                message,
                exc_info=exc,
            )
        try:
            await self._db.update_job(job.db_id, status="failed", error=message[:500])
        except Exception:
            log.exception("could not mark job %s failed in db", job.db_id)
        display_msg = (
            message
            if any(message.startswith(c) for c in ("🔒", "🔐", "🌍", "⏱", "📦", "🚫", "🔴", "💥", "🤫", "⌛️", "🛠", "❌"))
            else f"❌ {message}"
        )
        if job.reporter:
            await job.reporter.fail(display_msg)
        else:
            try:
                await self._send_text(job.chat_id, display_msg)
            except Exception:
                log.exception("could not deliver failure message for job %s", job.db_id)
        self._cleanup(job)
        self._jobs.pop(job.db_id, None)

    async def _cancelled(self, job: Job) -> None:
        self.counters["cancelled"] += 1
        log.info("job %s cancelled by user", job.db_id)
        try:
            await self._db.update_job(job.db_id, status="cancelled")
        except Exception:
            log.exception("could not mark job %s cancelled in db", job.db_id)
        if job.reporter:
            await job.reporter.finalize("🚫 Cancelled.")
        self._cleanup(job)
        self._jobs.pop(job.db_id, None)

    def _cleanup(self, job: Job) -> None:
        if job.tmp_dir is not None:
            remove_tree(job.tmp_dir)
            job.tmp_dir = None
