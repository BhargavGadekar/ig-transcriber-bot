"""Throttled, FloodWait-safe editing of a single status message.

One status message per job is created and edited in place through the stages
(Downloading → Extracting audio → Transcribing → Done / ❌). Edits are throttled
to at least MIN_EDIT_INTERVAL apart, and Telegram FloodWait errors are honoured
with a sleep + retry.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable, TypeVar

from pyrogram.errors import FloodWait, MessageNotModified, RPCError

log = logging.getLogger(__name__)

MIN_EDIT_INTERVAL = 3.0  # seconds between status-message edits

T = TypeVar("T")


async def send_with_flood_retry(factory: Callable[[], Awaitable[T]], *, attempts: int = 3) -> T:
    """Call an async factory, honouring FloodWait with exponential patience."""
    for attempt in range(attempts + 1):
        try:
            return await factory()
        except FloodWait as exc:
            if attempt == attempts:
                raise
            wait = float(getattr(exc, "value", 5)) + 0.5
            log.warning("FloodWait: sleeping %.1fs before retry", wait)
            await asyncio.sleep(wait)
    raise RuntimeError("unreachable")  # pragma: no cover


class StatusReporter:
    """Edits one Telegram message as job status, with throttling and backoff."""

    def __init__(self, client, chat_id: int, message_id: int):
        self._client = client
        self._chat_id = chat_id
        self._message_id = message_id
        self._loop = asyncio.get_running_loop()
        self._pending: str | None = None
        self._last_sent: str | None = None
        self._last_edit = 0.0
        self._closed = False
        self._dead = False  # message deleted/unreachable; stop editing
        self._flusher: asyncio.Task | None = None

    # -- public API (matches core.pipeline.ProgressReporter) -------------------

    def update(self, text: str) -> None:
        """Schedule a throttled status update (event-loop context only)."""
        if self._closed or self._dead:
            return
        self._pending = text
        self._ensure_flusher()

    def update_threadsafe(self, text: str) -> None:
        """Schedule an update from a worker thread (e.g. yt-dlp hook)."""
        try:
            self._loop.call_soon_threadsafe(self.update, text)
        except RuntimeError:
            pass  # loop shutting down

    async def finalize(self, text: str) -> None:
        """Force the final edit immediately."""
        await self._edit_final(text)

    async def fail(self, text: str) -> None:
        await self._edit_final(text)

    # -- internals ---------------------------------------------------------------

    def _ensure_flusher(self) -> None:
        if self._flusher is None or self._flusher.done():
            self._flusher = self._loop.create_task(self._flush_loop())

    async def _edit_final(self, text: str) -> None:
        self._closed = True
        if self._dead:
            return
        if self._flusher is not None:
            self._flusher.cancel()
            self._flusher = None
        try:
            await self._do_edit(text)
        except FloodWait as exc:
            wait = float(getattr(exc, "value", 5)) + 0.5
            log.warning("FloodWait on final edit: sleeping %.1fs", wait)
            await asyncio.sleep(wait)
            try:
                await self._do_edit(text)
            except (FloodWait, RPCError):
                log.exception("status message %s unreachable", self._message_id)
        except RPCError:
            self._dead = True
            log.debug("status message %s unreachable", self._message_id)
        self._last_sent = text
        self._pending = None
        self._last_edit = time.monotonic()

    async def _flush_loop(self) -> None:
        try:
            while not self._closed and not self._dead:
                await asyncio.sleep(0.5)
                if self._pending is None or self._pending == self._last_sent:
                    continue
                now = time.monotonic()
                if now - self._last_edit < MIN_EDIT_INTERVAL:
                    continue
                text = self._pending
                try:
                    await self._do_edit(text)
                except FloodWait as exc:
                    # Back off; try again after Telegram's demanded wait.
                    self._last_edit = now + float(getattr(exc, "value", 5))
                    continue
                except RPCError:
                    self._dead = True
                    return
                self._last_sent = text
                self._pending = None
                self._last_edit = time.monotonic()
        except asyncio.CancelledError:
            pass

    async def _do_edit(self, text: str) -> None:
        try:
            await self._client.edit_message_text(
                self._chat_id,
                self._message_id,
                text,
                disable_web_page_preview=True,
            )
        except MessageNotModified:
            pass
        except FloodWait:
            raise
        except RPCError as exc:
            # MESSAGE_ID_INVALID / message deleted → stop editing for good.
            self._dead = True
            log.debug("status message %s no longer editable: %s", self._message_id, exc)
