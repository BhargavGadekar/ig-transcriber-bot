import asyncio
from pathlib import Path
from unittest.mock import MagicMock
from core.config import Settings
from core.pipeline import Job, JobCancelled, JobManager

def test_job_cancellation():
    job = Job(db_id=1, user_id=10, chat_id=20, url="https://instagram.com/reel/123")
    job.throw_if_cancelled()  # should not raise
    job.cancel_event.set()
    try:
        job.throw_if_cancelled()
        assert False, "Expected JobCancelled"
    except JobCancelled:
        pass

def test_job_manager_start_stop(tmp_path: Path):
    async def run():
        settings = Settings(
            tg_api_id=1,
            tg_api_hash="h",
            tg_bot_token="t",
            data_dir=tmp_path / "data",
            worker_concurrency=2,
        )
        db = MagicMock()
        client = MagicMock()
        manager = JobManager(settings, db, client)

        await manager.start()
        stats = manager.stats()
        assert stats["workers"] == 2
        assert stats["queue_waiting"] == 0
        assert "llm" in stats
        assert stats["llm"]["last_status"] == "not_configured" 

        # Stop should cleanly terminate workers without ValueError
        await manager.stop(timeout=1.0)
        assert len(manager._jobs) == 0

    asyncio.run(run())


def test_send_media_video(tmp_path: Path):
    async def run():
        settings = Settings(
            tg_api_id=1,
            tg_api_hash="h",
            tg_bot_token="t",
            data_dir=tmp_path / "data",
        )
        db = MagicMock()
        client = MagicMock()
        manager = JobManager(settings, db, client)

        video_file = tmp_path / "test.mp4"
        video_file.write_bytes(b"dummy video data")

        from services.markdown import VideoMeta
        meta = VideoMeta(url="https://instagr.am/reel/1", title="Test Title", duration_s=15)

        await manager._send_media(12345, video_file, meta)
        client.send_video.assert_called_once()
        args, kwargs = client.send_video.call_args
        assert args[0] == 12345
        assert kwargs["video"] == str(video_file)
        assert kwargs["caption"] == "Test Title"
        assert kwargs["duration"] == 15
        assert kwargs["supports_streaming"] is True

    asyncio.run(run())

def test_job_manager_queue_capacity(tmp_path: Path):
    async def run():
        settings = Settings(
            tg_api_id=1,
            tg_api_hash="h",
            tg_bot_token="t",
            data_dir=tmp_path / "data",
            queue_max_size=2,
        )
        db = MagicMock()
        client = MagicMock()
        manager = JobManager(settings, db, client)

        j1 = Job(db_id=1, user_id=10, chat_id=20, url="https://instagram.com/reel/1")
        j2 = Job(db_id=2, user_id=10, chat_id=20, url="https://instagram.com/reel/2")
        j3 = Job(db_id=3, user_id=10, chat_id=20, url="https://instagram.com/reel/3")

        assert manager.submit(j1) is True
        assert manager.submit(j2) is True
        assert manager.submit(j3) is False

        await manager.stop(timeout=0.5)

    asyncio.run(run())
