import asyncio
import pytest
from unittest.mock import AsyncMock
from pyrogram.errors import FloodWait
from bot.progress import StatusReporter, send_with_flood_retry

def test_send_with_flood_retry():
    calls = 0
    async def factory():
        nonlocal calls
        calls += 1
        if calls == 1:
            err = FloodWait(value=0)
            raise err
        return "success"

    async def run():
        res = await send_with_flood_retry(factory, attempts=2)
        assert res == "success"
        assert calls == 2

    asyncio.run(run())

def test_status_reporter():
    async def run():
        client = AsyncMock()
        client.edit_message_text = AsyncMock()
        reporter = StatusReporter(client, chat_id=123, message_id=456)

        # Immediate update
        reporter.update("Step 1")
        assert reporter._pending == "Step 1"

        # Finalize
        await reporter.finalize("Done!")
        assert reporter._closed is True
        client.edit_message_text.assert_called_with(
            123, 456, "Done!", disable_web_page_preview=True
        )

    asyncio.run(run())
