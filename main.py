"""Entry point: wire config, logging, database, pipeline, health check and client.

Run with:  python main.py
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import signal
import sys
from pathlib import Path

from bot.client import build_client, set_bot_commands
from bot.handlers import register_handlers
from core.app import AppContext
from core.config import Settings
from core.database import Database
from core.health import start_health_server
from core.logging import configure_logging
from core.pipeline import JobManager
from utils.files import clean_dir_contents

log = logging.getLogger("main")


def warn_missing_dependencies(settings: Settings) -> None:
    """Log explicit warnings for anything missing; never crash startup."""
    whisper_bin = getattr(settings, "effective_whisper_bin", settings.whisper_bin)
    for tool in (whisper_bin, settings.ffmpeg_bin, settings.ffprobe_bin):
        if not (Path(tool).is_file() or shutil.which(tool)):
            log.warning("binary not found on PATH: %s — jobs will fail until fixed", tool)
    model_path = getattr(settings, "effective_model_path", settings.whisper_model_path)
    if not Path(model_path).is_file():
        log.warning(
            "whisper model not found at %s — run scripts/download_model.sh",
            model_path,
        )
    if settings.whisper_vad and not Path(settings.whisper_vad_model).is_file():
        log.warning(
            "VAD model not found at %s — run scripts/download_model.sh (whisper-cli "
            "may fall back to its own default)",
            settings.whisper_vad_model,
        )
    if settings.cookies_file and not Path(settings.cookies_file).is_file():
        log.warning(
            "COOKIES_FILE is set but %s does not exist — private/login-required "
            "Instagram content will fail until cookies are exported",
            settings.cookies_file,
        )


def _install_signal_handlers(stop_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:  # pragma: no cover - Windows
            signal.signal(sig, lambda *_: stop_event.set())


async def amain() -> None:
    settings = Settings()
    configure_logging(settings.log_dir, settings.log_level)
    settings.ensure_dirs()
    clean_dir_contents(settings.tmp_dir)  # purge leftovers from previous runs
    log.info(
        "starting ig-transcriber-bot (model=%s, threads=%d, workers=%d, "
        "script_mode=%s, vad=%s)",
        settings.whisper_model_name,
        settings.effective_threads,
        settings.worker_concurrency,
        settings.script_mode,
        settings.whisper_vad,
    )
    warn_missing_dependencies(settings)

    db = Database(settings.db_path)
    await db.connect()
    cleaned = await db.cleanup_stale_jobs()
    if cleaned > 0:
        log.info("cleaned up %d stale/interrupted jobs from previous run", cleaned)

    client = build_client(settings)
    jobs = JobManager(settings, db, client)
    await jobs.start()

    app = AppContext(settings=settings, db=db, jobs=jobs)
    register_handlers(client, app)

    health = None
    if settings.health_check_port:
        health = await start_health_server(settings.health_check_port, app.stats)

    stop_event = asyncio.Event()
    _install_signal_handlers(stop_event)

    await client.start()
    await set_bot_commands(client)
    me = await client.get_me()
    log.info(
        "bot is up as @%s — send it an Instagram link (health: 127.0.0.1:%d/health)",
        me.username,
        settings.health_check_port,
    )

    await stop_event.wait()
    log.info("shutdown signal received; finishing current work…")

    try:
        await asyncio.wait_for(jobs.stop(timeout=10), timeout=15)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        log.warning("forced worker shutdown after timeout")

    if health is not None:
        health.close()
    try:
        await client.stop()
    except Exception:
        log.exception("error stopping telegram client")
    await db.close()
    log.info("goodbye")


def main() -> int:
    try:
        asyncio.run(amain())
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception:
        logging.getLogger("main").exception("fatal startup error")
        return 1


if __name__ == "__main__":
    sys.exit(main())
