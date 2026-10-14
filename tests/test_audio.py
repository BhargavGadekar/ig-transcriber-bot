import asyncio
import pytest
from pathlib import Path
from services.audio import AudioError, extract_audio_wav, probe_duration_seconds

def test_audio_missing_binaries(tmp_path: Path):
    async def run():
        with pytest.raises(AudioError, match="ffmpeg binary not found"):
            await extract_audio_wav("in.mp4", "out.wav", ffmpeg_bin="nonexistent_ffmpeg_binary")

        dur = await probe_duration_seconds("test.mp4", ffprobe_bin="nonexistent_ffprobe_binary")
        assert dur is None

    asyncio.run(run())

def test_audio_real_extraction_if_available(tmp_path: Path):
    import shutil
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("ffmpeg or ffprobe not installed on host")

    async def run():
        # Generate a 1-second sine wave
        src = tmp_path / "sine.mp4"
        dst = tmp_path / "out.wav"
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
            str(src), stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
        )
        await proc.wait()
        assert src.is_file()

        # Probe duration
        duration = await probe_duration_seconds(src)
        assert duration is not None
        assert 0.9 <= duration <= 1.2

        # Extract wav
        await extract_audio_wav(src, dst)
        assert dst.is_file()
        assert dst.stat().st_size > 0

    asyncio.run(run())
