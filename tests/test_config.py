import pytest
from pathlib import Path
from pydantic import ValidationError
from core.config import Settings

def test_settings_valid(tmp_path: Path):
    s = Settings(
        tg_api_id=12345,
        tg_api_hash="dummy_hash",
        tg_bot_token="dummy_token",
        data_dir=tmp_path / "data",
        script_mode="roman",
        allowed_user_ids="111, 222; 333",
    )
    assert s.tg_api_id == 12345
    assert s.allowed_ids == frozenset({111, 222, 333})
    assert s.effective_threads >= 1
    assert s.max_filesize_bytes == 500 * 1024 * 1024
    assert s.rate_limit_per_hour == 0
    assert s.queue_max_size == 500
    assert s.whisper_no_mmap is False
    assert s.tmp_dir == tmp_path / "data" / "tmp"
    assert s.db_path == tmp_path / "data" / "bot.db"

    s.ensure_dirs()
    assert s.tmp_dir.is_dir()
    assert s.log_dir.is_dir()

def test_settings_invalid_script_mode():
    with pytest.raises(ValidationError):
        Settings(
            tg_api_id=1,
            tg_api_hash="h",
            tg_bot_token="t",
            script_mode="invalid_mode",
        )

def test_settings_invalid_allowed_ids():
    with pytest.raises(ValidationError):
        Settings(
            tg_api_id=1,
            tg_api_hash="h",
            tg_bot_token="t",
            allowed_user_ids="123, not_a_number",
        )

def test_effective_paths():
    s = Settings(
        tg_api_id=1,
        tg_api_hash="h",
        tg_bot_token="t",
        whisper_bin="nonexistent_whisper_bin_xyz",
        whisper_model_path="nonexistent_model_xyz.bin",
    )
    # Checks fallback or current value without crashing
    assert isinstance(s.effective_whisper_bin, str)
    assert isinstance(s.effective_model_path, Path)
