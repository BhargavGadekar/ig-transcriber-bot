"""Telegram message and command handlers."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable

from pyrogram import filters
from pyrogram.errors import MessageNotModified
from pyrogram.enums import ChatType
from pyrogram.handlers import CallbackQueryHandler, MessageHandler
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.progress import StatusReporter, send_with_flood_retry
from core.pipeline import Job
from utils.urls import extract_urls

if TYPE_CHECKING:  # pragma: no cover
    from pyrogram.client import Client

    from core.app import AppContext

log = logging.getLogger(__name__)

WELCOME = (
    "👋 Send me an Instagram reel / video or YouTube Short link and I'll transcribe it locally "
    "with whisper.cpp and send you an Obsidian-ready .md note.\n\n"
    "Examples:\n"
    "• https://www.instagram.com/reel/CxAbCdEf123/\n"
    "• https://youtube.com/shorts/dQw4w9WgXcQ\n\n"
    "/help — details • /status — queue • /settings — preferences"
)

HELP_TEXT = (
    "📚 **How to use**\n\n"
    "1. Send one or more Instagram or YouTube Shorts links (reel, post, IGTV, share link, youtube.com/shorts, youtu.be).\n"
    "2. Videos are downloaded in HD with natural 9:16 vertical preview.\n"
    "3. Photos and carousels are sent in order as an HD photo album.\n"
    "4. Videos include a [✅ Transcribe & Add to Notes] button to generate full Obsidian notes.\n\n"
    "**Commands**\n"
    "/status — queue length and your last job\n"
    "/settings — toggle timestamps, Hinglish script, and auto-transcribe mode\n"
    "/clean_drive — manually wipe downloaded videos to free disk space\n"
    "/cancel — cancel your queued or running jobs\n\n"
    "**Storage & Limits**\n"
    "• Videos stay on device up to 50 videos max (older ones auto-deleted FIFO) or until midnight IST\n"
    "• /clean_drive instantly frees all cached videos and temp files\n"
    "• Same link twice → instant cached result\n"
    "• Notes auto-save directly to your Obsidian vault\n"
)


def _human_uptime(seconds: float) -> str:
    seconds = int(seconds)
    hours, rem = divmod(seconds, 3600)
    minutes, _ = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m"
    return f"{seconds}s"


def _time_ago(iso_ts: str | None) -> str:
    if not iso_ts:
        return ""
    try:
        then = datetime.fromisoformat(iso_ts)
    except (ValueError, TypeError):
        return ""
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    delta = (datetime.now(timezone.utc) - then).total_seconds()
    return f"{_human_uptime(max(0, delta))} ago"


def register_handlers(client: "Client", app: "AppContext") -> None:
    """Attach all command/message/callback handlers to the client."""

    def command(name: str) -> Callable:
        return filters.command(name)

    async def _reply(message: Message, text: str) -> None:
        try:
            await send_with_flood_retry(
                lambda: message.reply_text(text, disable_web_page_preview=True)
            )
        except Exception:
            log.exception("failed to reply in chat %s", message.chat.id)

    # --- /start ---------------------------------------------------------------
    async def on_start(_client: "Client", message: Message) -> None:
        await _reply(message, WELCOME)

    # --- /help ------------------------------------------------------------------
    async def on_help(_client: "Client", message: Message) -> None:
        await _reply(message, HELP_TEXT)

    # --- /status ------------------------------------------------------------------
    async def on_status(_client: "Client", message: Message) -> None:
        user_id = message.from_user.id if message.from_user else message.chat.id
        stats = app.jobs.stats()
        last = await app.db.last_job_for_user(user_id)
        text = (
            "🤖 **Bot status**\n"
            f"Uptime: {_human_uptime(stats['uptime_s'])}\n"
            f"Queue: {stats['queue_waiting']} waiting • {stats['active_transcriptions']} transcribing "
            f"({stats['workers']} worker(s))\n"
            f"Session: {stats['jobs_done']} done • {stats['jobs_failed']} failed • "
            f"{stats['jobs_cached']} cached\n"
        )
        if last:
            text += (
                f"\n**Your last job**: {last.get('status')} — {last.get('url')} "
                f"({_time_ago(last.get('updated_at') or last.get('created_at'))})"
            )
        await _reply(message, text)

    # --- /settings -------------------------------------------------------------------
    async def _settings_text(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
        stored = await app.db.get_user_settings(user_id) or {}
        timestamps = stored.get("timestamps", app.settings.timestamps)
        script_mode = stored.get("script_mode", app.settings.script_mode)
        auto_tx = stored.get("auto_transcribe", app.settings.auto_transcribe)
        markup = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        f"⏱ Timestamps: {'ON' if timestamps else 'OFF'}",
                        callback_data="cfg:ts",
                    ),
                    InlineKeyboardButton(
                        "🅰 Script: Roman" if script_mode == "roman" else "🅰 Script: Native",
                        callback_data="cfg:script",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        f"⚡ Auto-Transcribe: {'ON' if auto_tx else 'OFF (On-Demand)'}",
                        callback_data="cfg:autotx",
                    ),
                ],
            ]
        )
        text = (
            "⚙️ **Your settings**\n\n"
            f"• Timestamps: {'ON' if timestamps else 'OFF'} — [mm:ss] markers in the transcript\n"
            f"• Script mode: {'Roman (romanized Hinglish)' if script_mode == 'roman' else 'Native (Devanagari for Hindi)'}\n"
            f"• Mode: {'Auto-transcribe every video' if auto_tx else 'On-demand (video first + [✅ Transcribe & Add to Notes] button)'}\n\n"
            "Tap a button to toggle."
        )
        return text, markup

    async def on_settings(_client: "Client", message: Message) -> None:
        user_id = message.from_user.id if message.from_user else message.chat.id
        text, markup = await _settings_text(user_id)
        try:
            await send_with_flood_retry(
                lambda: message.reply_text(text, reply_markup=markup,
                                           disable_web_page_preview=True)
            )
        except Exception:
            log.exception("failed to send settings panel")

    async def on_settings_callback(_client: "Client", callback_query) -> None:
        try:
            user_id = callback_query.from_user.id
            data = callback_query.data or ""
            stored = await app.db.get_user_settings(user_id) or {}
            timestamps = stored.get("timestamps", app.settings.timestamps)
            script_mode = stored.get("script_mode", app.settings.script_mode)
            auto_tx = stored.get("auto_transcribe", app.settings.auto_transcribe)
            if data == "cfg:ts":
                timestamps = not timestamps
            elif data == "cfg:script":
                script_mode = "native" if script_mode == "roman" else "roman"
            elif data == "cfg:autotx":
                auto_tx = not auto_tx
            else:
                await callback_query.answer()
                return
            await app.db.set_user_settings(
                user_id, timestamps=bool(timestamps), script_mode=script_mode, auto_transcribe=bool(auto_tx)
            )
            text, markup = await _settings_text(user_id)
            await send_with_flood_retry(
                lambda: callback_query.edit_message_text(
                    text, reply_markup=markup, disable_web_page_preview=True
                )
            )
            await callback_query.answer("Saved ✔")
        except MessageNotModified:
            try:
                await callback_query.answer("Saved ✔")
            except Exception:
                pass
        except Exception:
            log.exception("settings callback failed")
            try:
                await callback_query.answer("Failed — see logs")
            except Exception:
                pass

    # --- /clean_drive ----------------------------------------------------------------
    async def on_clean_drive(_client: "Client", message: Message) -> None:
        user_id = message.from_user.id if message.from_user else message.chat.id
        if app.settings.allowed_ids and user_id not in app.settings.allowed_ids:
            return
        from services.media_store import clean_drive
        deleted, freed = clean_drive(app.settings.downloads_dir, app.settings.tmp_dir)
        mb = freed / (1024 * 1024)
        await _reply(
            message,
            f"🧹 **Drive Cleaned!**\n"
            f"Removed **{deleted}** cached file(s).\n"
            f"Freed: **{mb:.1f} MB** of storage space."
        )

    # --- force transcribe callback ---------------------------------------------------
    async def on_force_transcribe_callback(_client: "Client", callback_query) -> None:
        try:
            user_id = callback_query.from_user.id
            if app.settings.allowed_ids and user_id not in app.settings.allowed_ids:
                await callback_query.answer("⛔ Unauthorized", show_alert=True)
                return
            job_id_str = callback_query.data.split(":", 1)[1]
            job_id = int(job_id_str)
            await callback_query.answer("Starting transcription & notes…")
            asyncio.create_task(
                app.jobs.force_transcribe_job(job_id, status_message=callback_query.message)
            )
        except Exception:
            log.exception("error handling force transcribe callback")
            try:
                await callback_query.answer("Failed to start transcription.")
            except Exception:
                pass

    # --- /cancel ---------------------------------------------------------------------
    async def on_cancel(_client: "Client", message: Message) -> None:
        user_id = message.from_user.id if message.from_user else message.chat.id
        counts = await app.jobs.cancel_user_jobs(user_id)
        queued, active = counts["queued"], counts["active"]
        if queued or active:
            parts = []
            if queued:
                parts.append(f"{queued} queued")
            if active:
                parts.append(f"{active} running")
            await _reply(message, f"🚫 Cancelling {' and '.join(parts)} job(s).")
        else:
            await _reply(message, "Nothing to cancel — you have no queued or running jobs.")

    # --- link messages -------------------------------------------------------------------
    async def on_message(_client: "Client", message: Message) -> None:
        try:
            await _handle_message(message, app)
        except Exception:
            log.exception("message handler failed")

    client.add_handler(MessageHandler(on_start, command("start")))
    client.add_handler(MessageHandler(on_help, command("help")))
    client.add_handler(MessageHandler(on_status, command("status")))
    client.add_handler(MessageHandler(on_settings, command("settings")))
    client.add_handler(MessageHandler(on_clean_drive, command("clean_drive")))
    client.add_handler(MessageHandler(on_cancel, command("cancel")))
    client.add_handler(CallbackQueryHandler(on_settings_callback, filters.regex(r"^cfg:")))
    client.add_handler(CallbackQueryHandler(on_force_transcribe_callback, filters.regex(r"^force_tx:")))
    client.add_handler(
        MessageHandler(
            on_message,
            filters.text | filters.caption,
        )
    )


async def _handle_message(message: Message, app: "AppContext") -> None:
    user = message.from_user
    if user is None:  # channel posts / anonymous forwards
        return
    user_id = user.id
    client = message._client  # noqa: SLF001 - pyrogram sets this on inbound updates

    async def reply(text: str) -> None:
        try:
            await send_with_flood_retry(
                lambda: message.reply_text(text, disable_web_page_preview=True)
            )
        except Exception:
            log.exception("failed to reply in chat %s", message.chat.id)

    if app.settings.allowed_ids and user_id not in app.settings.allowed_ids:
        log.warning("unauthorized access attempt by user %s", user_id)
        await reply("⛔ You're not authorized to use this bot.")
        return

    text = message.text or message.caption or ""
    urls = extract_urls(text)
    if not urls:
        if message.chat.type == ChatType.PRIVATE and text.strip():
            await reply(
                "Send me an Instagram reel / post or YouTube Short link and I'll "
                "transcribe it — e.g. https://www.instagram.com/reel/CxAbCdEf123/ or https://youtube.com/shorts/dQw4w9WgXcQ"
            )
        return

    if app.settings.rate_limit_per_hour > 0:
        recent = await app.db.count_recent_jobs(user_id, hours=1)
        if recent >= app.settings.rate_limit_per_hour:
            await reply(
                f"⏳ Rate limit reached ({app.settings.rate_limit_per_hour} links/hour). "
                "Please try again later."
            )
            return

    for url in urls[: app.settings.max_links_per_message]:
        await _start_job(message, app, url)


async def _start_job(message: Message, app: "AppContext", url: str) -> None:
    client = message._client  # noqa: SLF001
    user_id = message.from_user.id
    chat_id = message.chat.id

    db_id = await app.db.add_job(user_id, chat_id, message.id, url)
    cached = await app.db.get_transcript(url)
    job = Job(db_id=db_id, user_id=user_id, chat_id=chat_id, message_id=message.id, url=url)

    if cached:
        await app.db.update_job(db_id, status="cached")
        task = asyncio.create_task(app.jobs.serve_cached(job, cached[0], cached[1]))
        task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
        return

    reporter: StatusReporter | None = None
    try:
        status = await send_with_flood_retry(
            lambda: message.reply_text("⬇️ Downloading…", disable_web_page_preview=True)
        )
        reporter = StatusReporter(client, chat_id, status.id)
    except Exception:
        log.warning("could not create status message for job %s", db_id)
    job.reporter = reporter
    app.jobs.submit(job)
