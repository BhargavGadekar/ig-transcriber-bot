# ig-transcriber-bot

Send an Instagram reel/video link to a Telegram bot → get back an Obsidian-ready `.md` note with video metadata, clean local transcription (whisper.cpp), AI-powered executive summary (Gemini / OpenAI), and the downloaded media file.

Works with English, Hindi, Hinglish, and 90+ other languages Whisper supports.

```
you:  https://www.instagram.com/reel/CxAbCdEf123/
bot:  ⬇️ Downloading… → 🎧 Extracting audio… → ✍️ Transcribing… → 🧠 Summarizing…
bot:  📹 [Delivered Video File]
bot:  💡 Executive Summary & Key Takeaways
bot:  📝 Preview (Restored Hinglish / English)
bot:  📄 2026-10-14_creator_9f3ab2c1.md
```

---

## 🚀 Quickstart: Clone & Run

### 1. Clone & Set Up Python Environment

```bash
git clone https://github.com/BhargavGadekar/ig-transcriber-bot.git
cd ig-transcriber-bot

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Install Dependencies & Build whisper.cpp

Make sure `ffmpeg` is installed on your system:
```bash
# macOS
brew install ffmpeg cmake

# Ubuntu / Debian
sudo apt update && sudo apt install -y ffmpeg cmake build-essential
```

Compile `whisper-cli` locally (enables Metal GPU acceleration on Apple Silicon or multithreading on Linux):
```bash
bash scripts/install_whisper_cpp.sh
```

---

## 🧠 Which Model to Use & Where to Put It

All Whisper and VAD models **must be placed in the `models/` folder** in the project root.

### Recommended Model: `large-v3-turbo-q5_0`

| Model | Disk Size | RAM Usage | Best For |
|---|---|---|---|
| **`large-v3-turbo-q5_0`** *(Recommended)* | **574 MB** | **~1.6 GB** | **Best balance of accuracy, speed, and low memory.** Excellent for English, Hindi, and multilingual audio. |
| `small` | 466 MB | ~850 MB | Low-RAM budget VPS (1GB–2GB RAM without swap). |
| `medium-q5_0` | 1.5 GB | ~2.1 GB | Higher accuracy when more RAM is available. |
| `large-v3` | 3.1 GB | ~4.5 GB | Maximum transcription accuracy (requires 8GB+ RAM or GPU). |

### Automatic 1-Command Download

Download the recommended transcription model along with the Silero VAD (voice activity detection) model:

```bash
# Downloads ggml-large-v3-turbo-q5_0.bin and ggml-silero-v6.2.0.bin into models/
bash scripts/download_model.sh large-v3-turbo-q5_0
```

This populates the `models/` directory:
```
models/
├── ggml-large-v3-turbo-q5_0.bin    # Whisper speech recognition model
└── ggml-silero-v6.2.0.bin           # Silero VAD (cuts silence & music hallucinations)
```

*(Manual download from Hugging Face: [large-v3-turbo-q5_0](https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo-q5_0.bin) and [silero-vad](https://huggingface.co/ggml-org/whisper-vad/resolve/main/ggml-silero-v6.2.0.bin))*

---

## ⚙️ Configuration (`.env`)

Copy the example configuration file:
```bash
cp .env.example .env
```

Open `.env` and fill in the required fields:

### 1. Telegram Credentials (Required)
* `TG_API_ID` & `TG_API_HASH`: Get from [my.telegram.org](https://my.telegram.org) under API development tools.
* `TG_BOT_TOKEN`: Create a bot via [@BotFather](https://t.me/BotFather).
* `ALLOWED_USER_IDS`: Your numeric Telegram user ID (comma-separated; leave empty to allow everyone).

### 2. AI Summarization & Hinglish Restoration (Optional, Free Tier Supported)
Supports **Google Gemini** (recommended, free tier) or any OpenAI-compatible provider (Groq, OpenRouter, DeepSeek, Ollama, OpenAI):

```env
# Google Gemini (Free tier from Google AI Studio)
LLM_API_KEY=your_gemini_api_key_here
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
LLM_MODEL=gemini-3.1-flash-lite
```

> **Why this matters for Hinglish:** Whisper transcribes Hindi/Urdu speech into Perso-Arabic or Devanagari script. Direct Latin transliteration often produces vowel-less phonetic text (`andin jnzi` $\rightarrow$ `Indian Gen-Z`, `alikshn kmishn` $\rightarrow$ `Election Commission`, `rizaئn` $\rightarrow$ `resign`, `protist` $\rightarrow$ `protest`). When Gemini is configured, it automatically restores the transcript into natural, fluent Roman Hinglish and generates an Obsidian callout summary (`> [!summary]`).

### 3. Model Paths (Default matches download script)
```env
WHISPER_BIN=third_party/whisper.cpp/build/bin/whisper-cli
WHISPER_MODEL_PATH=models/ggml-large-v3-turbo-q5_0.bin
WHISPER_MODEL_NAME=large-v3-turbo-q5_0
WHISPER_VAD_MODEL=models/ggml-silero-v6.2.0.bin
WHISPER_VAD=true
```

---

## ▶️ Running the Bot

### Local / Development
```bash
python main.py
```

### Turnkey VPS Deployment (Ubuntu / Debian, 2GB+ RAM)
The repository includes an automated VPS deployment script that configures system dependencies, compiles whisper.cpp, downloads models, sets up a 2GB swapfile if RAM $\le 2.5$GB, and registers a `systemd` service:

```bash
bash scripts/deploy_vps.sh
```

### Docker Compose
```bash
docker compose up -d --build
```

---

## 🍪 Instagram Cookies (`cookies.txt`)

Instagram gates many reels behind login or age verification. Providing a `cookies.txt` ensures reliable downloads:

1. Install the browser extension **"Get cookies.txt LOCALLY"** (Chrome / Firefox).
2. Log into instagram.com with a **secondary or throwaway account** (never your primary account).
3. Open the extension and click **Export** (Netscape format).
4. Save the file to `data/cookies.txt` (or set `COOKIES_FILE=data/cookies.txt` in `.env`).

---

## 📁 Architecture Overview

```
main.py                 entry point: config → logging → database → workers → bot client
bot/                    Telegram interface (pyrofork)
  client.py             Bot initialization & command registration
  handlers.py           /start, /help, /status, /settings, /cancel & reel link intake
  progress.py           Live throttled Telegram status cards (FloodWait-safe)
services/
  downloader.py         yt-dlp wrapper with cookie support & friendly error messages
  audio.py              ffmpeg extraction (16 kHz mono PCM WAV)
  transcriber.py        whisper-cli runner with Silero VAD & progress parsing
  summarizer.py         Gemini & OpenAI LLM summarization + Hinglish restoration
  markdown.py           Obsidian-ready markdown note generator (YAML frontmatter + body)
core/
  config.py             Pydantic settings with auto-provider detection
  database.py           Async SQLite storage for jobs, transcript caching, and settings
  pipeline.py           Job manager orchestrating parallel downloads & CPU worker queue
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
venv/bin/pytest tests/ -v
```
All 93 tests cover URL parsing, audio conversion, transcription, summarizer failover, dual-output parsing, and markdown rendering.

---

## 📜 License

MIT License. Built for personal note-taking and knowledge archiving.
