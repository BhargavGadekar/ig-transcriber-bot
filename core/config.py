"""Application settings via pydantic-settings (.env / environment variables).

Every field maps to an uppercase environment variable of the same name.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_ROMAN_PROMPT = (
    "Yeh ek Hinglish video hai. Hindi and English mixed, written in Roman script."
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Telegram -----------------------------------------------------------
    tg_api_id: int = Field(..., description="api_id from https://my.telegram.org")
    tg_api_hash: str = Field(..., description="api_hash from https://my.telegram.org")
    tg_bot_token: str = Field(..., description="Bot token from @BotFather")
    session_name: str = "igtranscriber"
    allowed_user_ids: str = ""  # comma-separated; empty = open to everyone

    # --- Platform / Machine Optimization ------------------------------------
    on_mac: bool = True  # enable high-concurrency Mac parallel processing
    is_mac: bool = True  # alias for on_mac

    # --- Paths ----------------------------------------------------------------
    data_dir: Path = Path("data")
    downloads_dir: Path = Path("data/downloads")
    max_downloaded_videos: int = 50  # FIFO ring buffer: keep max 50 videos on device
    cookies_file: str = ""  # Netscape cookies.txt exported for instagram.com
    # Optional: save copies of generated .md files (e.g. your Obsidian vault)
    md_output_dir: str = ""

    # --- whisper.cpp ----------------------------------------------------------
    whisper_bin: str = "whisper-cli"
    whisper_model_path: Path = Path("models/ggml-large-v3-turbo-q5_0.bin")
    whisper_model_name: str = "large-v3-turbo-q5_0"
    whisper_vad_model: Path = Path("models/ggml-silero-v6.2.0.bin")
    whisper_vad: bool = True
    whisper_threads: int = 0  # 0 → auto (all CPUs minus one)
    whisper_max_context: int = 0  # 0 disables context carry-over; -1 = whisper default
    whisper_extra_args: str = ""  # extra CLI args, shlex-split
    whisper_timeout_base: int = 600  # seconds
    whisper_timeout_per_second: float = 15.0  # + this many seconds per audio second
    whisper_no_mmap: bool = False  # false = mmap enabled (saves physical RAM on Linux VPS)

    # --- Transcript rendering --------------------------------------------------
    script_mode: str = "roman"  # roman | native
    roman_prompt: str = DEFAULT_ROMAN_PROMPT
    timestamps: bool = True
    timestamp_interval_seconds: int = 45
    transcript_keep_tags: bool = False  # keep [MUSIC]-style tags if true
    preview_max_chars: int = 3500
    auto_transcribe: bool = False  # false = download & send video with button; true = auto-transcribe

    # --- AI Summarization (LLM) ------------------------------------------------
    llm_api_key: str = ""  # Google Gemini API key or any OpenAI-compatible key
    gemini_api_key: str = ""  # alias for Google Gemini key
    openai_api_key: str = ""  # alias for OpenAI key
    llm_fallback_api_key: str = ""  # Fallback key on quota exhaustion
    gemini_fallback_api_key: str = ""  # alias for Gemini fallback key
    llm_base_url: str = ""  # custom base URL (e.g. OpenAI, Groq, Ollama, OpenRouter)
    llm_model: str = ""  # model name override (e.g. gemini-2.5-flash, gpt-4o-mini)
    llm_timeout_seconds: int = 45

    # --- Limits & concurrency ---------------------------------------------------
    max_duration_seconds: int = 1200  # 20 minutes
    max_filesize_mb: int = 500
    rate_limit_per_hour: int = 0  # 0 = unlimited (disabled)
    queue_max_size: int = 500  # maximum queue capacity (waiting + active)
    worker_concurrency: int = 1  # transcription workers (1 is optimal for 2GB RAM VPS)
    download_concurrency: int = 2
    max_links_per_message: int = 25  # batch pasting support

    # --- Tooling / ops -----------------------------------------------------------
    ffmpeg_bin: str = "ffmpeg"
    ffprobe_bin: str = "ffprobe"
    health_check_port: int = 8080  # 0 disables
    log_level: str = "INFO"

    @field_validator("script_mode")
    @classmethod
    def _validate_script_mode(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in ("roman", "native"):
            raise ValueError("script_mode must be 'roman' or 'native'")
        return value

    @field_validator("allowed_user_ids")
    @classmethod
    def _validate_allowed_ids(cls, value: str) -> str:
        for part in value.replace(";", ",").split(","):
            part = part.strip()
            if part:
                int(part)  # raises ValueError on junk
        return value

    @property
    def allowed_ids(self) -> frozenset[int]:
        return frozenset(
            int(part.strip())
            for part in self.allowed_user_ids.replace(";", ",").split(",")
            if part.strip()
        )

    @property
    def effective_whisper_bin(self) -> str:
        if Path(self.whisper_bin).is_file() or shutil.which(self.whisper_bin):
            return self.whisper_bin
        built_bin = Path("third_party/whisper.cpp/build/bin/whisper-cli")
        if built_bin.is_file():
            return str(built_bin)
        return self.whisper_bin

    @property
    def effective_model_path(self) -> Path:
        p = Path(self.whisper_model_path)
        if p.is_file():
            return p
        for candidate in ("models/ggml-tiny.bin", "models/ggml-base.bin", "models/ggml-small.bin"):
            cp = Path(candidate)
            if cp.is_file():
                return cp
        return p

    @property
    def effective_worker_concurrency(self) -> int:
        if self.worker_concurrency > 1:
            return self.worker_concurrency
        if self.on_mac or self.is_mac:
            # 3 parallel transcription workers on Mac Apple Silicon (16GB RAM + Metal)
            return 3
        return 1

    @property
    def effective_download_concurrency(self) -> int:
        if self.download_concurrency > 2:
            return self.download_concurrency
        if self.on_mac or self.is_mac:
            return 4
        return 2

    @property
    def effective_threads(self) -> int:
        if self.whisper_threads > 0:
            return self.whisper_threads
        cpus = os.cpu_count() or 1
        workers = self.effective_worker_concurrency
        if (self.on_mac or self.is_mac) and workers > 1:
            # Distribute CPU cores among parallel workers (e.g. 10 cores -> 4 threads each)
            return max(2, min(6, (cpus + workers - 1) // workers + 1))
        # On VPS with <= 4 cores, use all available cores for fast transcription.
        # On machines with > 4 cores, leave 1 core for I/O and OS.
        return min(4, cpus) if cpus <= 4 else max(1, cpus - 1)

    @property
    def effective_llm_api_key(self) -> str:
        return (
            self.llm_api_key.strip()
            or self.gemini_api_key.strip()
            or self.openai_api_key.strip()
            or os.environ.get("LLM_API_KEY", "").strip()
            or os.environ.get("GEMINI_API_KEY", "").strip()
            or os.environ.get("OPENAI_API_KEY", "").strip()
        )

    @property
    def effective_llm_api_keys(self) -> list[str]:
        keys: list[str] = []
        primary = self.effective_llm_api_key
        if primary:
            keys.append(primary)
            fallback = (
                self.llm_fallback_api_key.strip()
                or self.gemini_fallback_api_key.strip()
                or os.environ.get("LLM_FALLBACK_API_KEY", "").strip()
                or os.environ.get("GEMINI_FALLBACK_API_KEY", "").strip()
            )
            if fallback and fallback not in keys:
                keys.append(fallback)
        return keys

    @property
    def effective_llm_provider(self) -> str:
        key = self.effective_llm_api_key
        url = self.llm_base_url.strip().lower()
        model = self.llm_model.strip().lower()
        if not key:
            return "none"
        if "openai.com" in url or key.startswith("sk-"):
            return "openai"
        if "groq.com" in url or key.startswith("gsk_"):
            return "groq"
        if "googleapis.com" in url or key.startswith("AIza") or key.startswith("AQ.") or "gemini" in model:
            return "gemini"
        if "openrouter" in url:
            return "openrouter"
        if "deepseek" in url:
            return "deepseek"
        return "custom"

    @property
    def effective_llm_base_url(self) -> str:
        if self.llm_base_url.strip():
            return self.llm_base_url.strip().rstrip("/")
        provider = self.effective_llm_provider
        if provider == "gemini":
            return "https://generativelanguage.googleapis.com/v1beta/openai"
        if provider == "groq":
            return "https://api.groq.com/openai/v1"
        return "https://api.openai.com/v1"

    @property
    def effective_llm_model(self) -> str:
        raw = self.llm_model.strip()
        if raw:
            if raw.lower() in ("gemini-3-flash", "models/gemini-3-flash"):
                return "gemini-3-flash-preview"
            if raw.lower() in ("gemini-2.5-flash", "models/gemini-2.5-flash"):
                return "gemini-2.5-flash"
            return raw
        provider = self.effective_llm_provider
        if provider == "gemini":
            return "gemini-3-flash-preview"
        if provider == "groq":
            return "llama-3.3-70b-versatile"
        return "gpt-4o-mini"

    @property
    def max_filesize_bytes(self) -> int:
        return self.max_filesize_mb * 1024 * 1024

    @property
    def tmp_dir(self) -> Path:
        return self.data_dir / "tmp"

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "bot.db"

    def ensure_dirs(self) -> None:
        for path in (self.data_dir, self.tmp_dir, self.log_dir, self.downloads_dir):
            path.mkdir(parents=True, exist_ok=True)
        if self.md_output_dir:
            Path(self.md_output_dir).mkdir(parents=True, exist_ok=True)
