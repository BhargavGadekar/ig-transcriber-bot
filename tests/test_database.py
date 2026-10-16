import asyncio
import pytest
from pathlib import Path
from core.database import Database

def test_database_lifecycle(tmp_path: Path):
    async def run():
        db_file = tmp_path / "test.db"
        db = Database(db_file)
        with pytest.raises(RuntimeError):
            _ = db.conn

        await db.connect()
        assert db.conn is not None

        # Job lifecycle
        jid = await db.add_job(user_id=1, chat_id=10, message_id=100, url="https://instagram.com/reel/abc")
        assert jid > 0
        await db.update_job(jid, status="transcribing", md_filename="test.md")
        last = await db.last_job_for_user(1)
        assert last is not None
        assert last["status"] == "transcribing"
        assert last["md_filename"] == "test.md"

        # Rate limiting counter
        assert await db.count_recent_jobs(1, hours=1) == 1
        assert await db.count_recent_jobs(999, hours=1) == 0

        # Transcripts cache
        assert await db.get_transcript("https://instagram.com/reel/abc") is None
        await db.put_transcript("https://instagram.com/reel/abc", {"title": "My Reel"}, [{"text": "Hi"}])
        cached = await db.get_transcript("https://instagram.com/reel/abc")
        assert cached is not None
        assert cached[0]["title"] == "My Reel"
        assert cached[1][0]["text"] == "Hi"

        # User settings
        assert await db.get_user_settings(1) is None
        await db.set_user_settings(1, timestamps=False, script_mode="native", auto_transcribe=False)
        s1 = await db.get_user_settings(1)
        assert s1 == {"timestamps": False, "script_mode": "native", "auto_transcribe": False}
        # Conflict update
        await db.set_user_settings(1, timestamps=True, script_mode="roman", auto_transcribe=True)
        s2 = await db.get_user_settings(1)
        assert s2 == {"timestamps": True, "script_mode": "roman", "auto_transcribe": True}

        
        # Cleanup stale jobs
        j_stale = await db.add_job(user_id=2, chat_id=20, message_id=200, url="https://instagram.com/reel/stale")
        await db.update_job(j_stale, status="downloading")
        cleaned_cnt = await db.cleanup_stale_jobs()
        assert cleaned_cnt >= 1
        stale_record = await db.last_job_for_user(2)
        assert stale_record["status"] == "failed"
        assert "Interrupted" in stale_record["error"]

        await db.close()
        assert db._conn is None

    asyncio.run(run())
