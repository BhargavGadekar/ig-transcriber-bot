"""Pyrogram (pyrofork) client construction and startup niceties."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pyrogram import Client

if TYPE_CHECKING:  # pragma: no cover
    from core.config import Settings

log = logging.getLogger(__name__)


def build_client(settings: "Settings") -> Client:
    return Client(
        settings.session_name,
        api_id=settings.tg_api_id,
        api_hash=settings.tg_api_hash,
        bot_token=settings.tg_bot_token,
        workdir=str(settings.data_dir),
    )


async def set_bot_commands(client: Client) -> None:
    from pyrogram.types import BotCommand

    commands = [
        BotCommand("start", "Start the bot and see usage"),
        BotCommand("help", "How to use the bot"),
        BotCommand("status", "Queue length and your last job"),
        BotCommand("settings", "Toggle timestamps, script & auto-transcribe"),
        BotCommand("clean_drive", "Clear downloaded videos to free disk space"),
        BotCommand("cancel", "Cancel your queued/running jobs"),
    ]
    try:
        await client.set_bot_commands(commands)
    except Exception:
        log.warning("could not set bot commands", exc_info=True)
