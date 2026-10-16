# ig-transcriber-bot

Send an Instagram reel, video, carousel or YouTube Shorts link to a Telegram bot → get back:
- 📹 **Natural 9:16 HD Media**: Probed with `ffprobe` and delivered with auto-generated frame thumbnails (`ffmpeg`) — eliminating black-out square boxes in Telegram for both Instagram Reels and YouTube Shorts.
- 🔴 **YouTube Shorts & Instagram Reels**: Seamlessly supports `youtube.com/shorts/...`, `youtu.be/...`, and all Instagram video formats with canonical de-duplication.
- 🖼️ **Ordered Photo & Carousel Albums**: Multiple images delivered in original order as an HD Telegram album without unnecessary transcription.
- 📓 **Obsidian-Ready Notes**: Automatically synced to your Obsidian vault via Google Drive or local path (`MD_OUTPUT_DIR`) with YAML frontmatter, executive summary callouts, key book references (`*[[Book Title]]*`), facts, mental models, and actionable takeaways (`> [!tip]`).
- ✍️ **Local Speech Transcription**: Powered by `whisper.cpp` with Silero VAD (voice activity detection) supporting English, Hindi, Roman Hinglish, and 90+ languages.
- 🔘 **On-Demand & Music Support**: Music-only videos and videos without speech include a `[✅ Transcribe & Add to Notes]` button. Users can also configure On-Demand mode in `/settings`.
- 🗄️ **Smart Storage Retention**: 50-video FIFO ring buffer (when 51st arrives, 1st oldest auto-evicts), background midnight IST auto-cleanup, and manual `/clean_drive` purging.
- ⚡ **Apple Silicon Metal Optimization**: Automatic multi-worker concurrency (3 parallel workers on M-series Macs) and dual Gemini API key failover.

```
you:  https://www.youtube.com/shorts/dQw4w9WgXcQ (or instagram.com/reel/...)
bot:  ⬇️ Downloading… → 🎧 Extracting audio… → ✍️ Transcribing… → 🧠 Summarizing…
bot:  📹 [Delivered 9:16 Video with Preview Frame]
bot:  💡 Executive Summary & Key Takeaways
bot:  📝 Preview (Restored Hinglish / English)
bot:  📄 2026-10-14_creator_9f3ab2c1.md
```

---

## 🚀 Deployment Sequence

### Option A: Local / Mac Deployment (Recommended for Apple Silicon)

Follow this deployment sequence to run the bot locally with Apple Silicon Metal GPU acceleration and automatic Obsidian syncing:

```bash
# 1. Clone repository
git clone https://github.com/BhargavGadekar/ig-transcriber-bot.git
cd ig-transcriber-bot

# 2. Set up Python virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Install ffmpeg & cmake (if not installed)
brew install ffmpeg cmake

# 4. Compile whisper.cpp with Metal GPU acceleration
bash scripts/install_whisper_cpp.sh

# 5. Download recommended Whisper & Silero VAD models
bash scripts/download_model.sh large-v3-turbo-q5_0

# 6. Configure environment variables
cp .env.example .env
# Edit .env with your Telegram credentials and Gemini API keys

# 7. Run the test suite (112 unit tests)
./venv/bin/pytest tests/ -v

# 8. Start the bot
./venv/bin/python main.py
```

### Option B: Linux VPS Deployment (Ubuntu / Debian, 2GB+ RAM)

Use the automated turnkey deployment script which installs dependencies, builds whisper.cpp, downloads models, configures a swapfile, and sets up a `systemd` service:

```bash
# 1. Clone & enter directory
git clone https://github.com/BhargavGadekar/ig-transcriber-bot.git
cd ig-transcriber-bot

# 2. Configure .env
cp .env.example .env
nano .env

# 3. Run automated turnkey VPS setup
bash scripts/deploy_vps.sh

# 4. Control systemd service
sudo systemctl status ig-transcriber-bot
sudo systemctl restart ig-transcriber-bot
sudo journalctl -u ig-transcriber-bot -f
```

### Option C: Docker Compose

```bash
docker compose up -d --build
```

---

## 🧠 Whisper & VAD Models

All models reside in `models/`.

### Recommended Model: `large-v3-turbo-q5_0`

| Model | Disk Size | RAM Usage | Best For |
|---|---|---|---|
| **`large-v3-turbo-q5_0`** *(Recommended)* | **574 MB** | **~1.6 GB** | **Best balance of accuracy, speed, and low memory.** Excellent for English, Hindi, and multilingual audio. |
| `small` | 466 MB | ~850 MB | Low-RAM budget VPS (1GB–2GB RAM without swap). |
| `medium-q5_0` | 1.5 GB | ~2.1 GB | Higher accuracy when more RAM is available. |
| `large-v3` | 3.1 GB | ~4.5 GB | Maximum transcription accuracy (requires 8GB+ RAM or GPU). |

Download transcription + VAD models with one command:
```bash
bash scripts/download_model.sh large-v3-turbo-q5_0
```

---

## ⚙️ Configuration (`.env`)

```env
# --- Telegram Bot Credentials ---
TG_API_ID=your_api_id
TG_API_HASH=your_api_hash
TG_BOT_TOKEN=your_bot_token
ALLOWED_USER_IDS=your_numeric_user_id

# --- Hardware & Concurrency ---
ON_MAC=true                     # Enables 3 parallel workers & 4 download slots on Mac
WORKER_CONCURRENCY=3
DOWNLOAD_CONCURRENCY=4

# --- AI Summarizer & 6-Tier Model/Account Failover ---
# Cascade: gemini-3-flash (Acc 1 -> Acc 2) -> gemini-3.1-flash-lite (Acc 1 -> Acc 2) -> gemini-2.5-flash (Acc 1 -> Acc 2)
LLM_API_KEY=your_primary_gemini_key
LLM_FALLBACK_API_KEY=your_backup_gemini_key
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
LLM_MODEL=gemini-3-flash

# --- Storage & Obsidian Vault Sync ---
MD_OUTPUT_DIR="/Users/yourname/Library/CloudStorage/GoogleDrive-.../My Drive/Master Obsidian/Lifebook/Reels"
MAX_DOWNLOADED_VIDEOS=50        # FIFO ring buffer limit
AUTO_TRANSCRIBE=false           # false = instant video + button; true = auto-transcribe speech

# --- whisper.cpp & VAD Paths ---
WHISPER_BIN=third_party/whisper.cpp/build/bin/whisper-cli
WHISPER_MODEL_PATH=models/ggml-large-v3-turbo-q5_0.bin
WHISPER_MODEL_NAME=large-v3-turbo-q5_0
WHISPER_VAD_MODEL=models/ggml-silero-v6.2.0.bin
WHISPER_VAD=true
```

---

## 🎮 Telegram Bot Commands

| Command | Description |
|---|---|
| `/start` | Welcome message and quick instructions. |
| `/help` | Detailed feature list, storage limits, and usage guide. |
| `/status` | Active queue length, workers, uptime, and last processed job. |
| `/settings` | Interactive buttons: toggle timestamps, Hinglish script (Roman/Native), and Auto-Transcribe vs. On-Demand mode. |
| `/clean_drive` | Manually clears cached video files in `data/downloads/` and reports megabytes freed. |
| `/cancel` | Cancels any queued or running jobs for your user ID. |

---

## 📁 Architecture Overview

```
main.py                 entry point: config → logging → database → workers → bot client
bot/                    Telegram interface (pyrofork)
  client.py             Bot initialization & command registration
  handlers.py           /start, /help, /status, /settings, /clean_drive, /cancel & callback handlers
  progress.py           Live throttled Telegram status cards (FloodWait-safe)
services/
  downloader.py         yt-dlp wrapper with cookie support, HD photo carousel extraction & error handling
  video.py              ffprobe video metadata (dimensions/aspect ratio) & ffmpeg thumbnail frame extractor
  media_store.py        Persistent video storage, 50-video FIFO ring buffer, midnight IST cleanup & clean_drive
  audio.py              ffmpeg extraction (16 kHz mono PCM WAV)
  transcriber.py        whisper-cli runner with Silero VAD & progress parsing
  summarizer.py         Gemini & OpenAI LLM summarizer with dual key failover & Obsidian book references
  markdown.py           Obsidian-ready markdown note generator (YAML frontmatter + body)
core/
  config.py             Pydantic settings with hardware detection and env validation
  database.py           Async SQLite storage for jobs, transcript caching, and user settings
  pipeline.py           Job manager orchestrating parallel downloads, delivery, and transcription workers
  health.py             HTTP health check endpoint (default: 127.0.0.1:8080/health)
utils/                  URL normalization, text cleanup, Hinglish transliteration, languages
scripts/
  download_model.sh     One-command model downloader (Whisper + Silero VAD)
  install_whisper_cpp.sh Compiles whisper.cpp locally with Metal / OpenBLAS
  deploy_vps.sh         Automated Ubuntu/Debian production setup script
```

---

## 🧪 Testing

Run the automated test suite:
```bash
./venv/bin/pytest tests/ -v
```
All 112 tests cover:
- YouTube Shorts and Instagram URL extraction, normalization, and canonical deduplication (`test_urls.py`)
- Aspect ratio probing and thumbnail generation fallback (`test_video.py`)
- Persistent media storage, FIFO ring buffer, and midnight IST cleanups (`test_media_store.py`)
- URL normalization, Hinglish transliteration, and text processing
- SQLite database migrations, job lifecycle, and user preferences (`test_database.py`)
- Whisper CLI execution and Silero VAD parameters
- LLM summarization, dual-key failover, and Obsidian markdown rendering

---

## 📜 License

MIT License. Built for personal note-taking and knowledge archiving.
