from pathlib import Path
from core.config import Settings
from services.transcriber import (
    _fail,
    _K,
    build_command,
    TranscribeFailure,
    WhisperResult,
)

def test_build_command(tmp_path: Path):
    settings = Settings(
        tg_api_id=1,
        tg_api_hash="h",
        tg_bot_token="t",
        whisper_bin="whisper-cli",
        whisper_model_path=tmp_path / "model.bin",
        whisper_vad=True,
        whisper_vad_model=tmp_path / "vad.bin",
        script_mode="roman",
        roman_prompt="Test Prompt",
        whisper_threads=4,
        whisper_max_context=0,
        whisper_extra_args="--beam-size 2",
    )
    (tmp_path / "vad.bin").touch()

    wav = tmp_path / "in.wav"
    out = tmp_path / "out"
    cmd = build_command(settings, wav, out)

    assert "whisper-cli" in cmd[0]
    assert "-m" in cmd
    assert "-f" in cmd
    assert "-t" in cmd and "4" in cmd
    assert "--vad" in cmd
    assert "-vm" in cmd
    assert "--prompt" in cmd and "Test Prompt" in cmd
    assert "--max-context" in cmd and "0" in cmd
    assert "--beam-size" in cmd and "2" in cmd
    assert "-osrt" in cmd
    assert "-ojf" in cmd

def test_transcribe_failure_kinds():
    f_speech = _fail(_K.NO_SPEECH)
    assert "No speech detected" in f_speech.user_message

    f_timeout = _fail(_K.TIMEOUT)
    assert "timed out" in f_timeout.user_message

    f_bin = _fail(_K.BIN_MISSING)
    assert "not found" in f_bin.user_message

def test_build_command_no_mmap(tmp_path: Path):
    settings = Settings(
        tg_api_id=1,
        tg_api_hash="h",
        tg_bot_token="t",
        whisper_bin="whisper-cli",
        whisper_model_path=tmp_path / "model.bin",
        whisper_no_mmap=True,
    )
    cmd = build_command(settings, tmp_path / "in.wav", tmp_path / "out")
    assert "--no-mmap" in cmd
