# Manual test checklist

Run after setup (and after any yt-dlp/whisper.cpp update). Each case sends a
link to the running bot and checks the reply end to end. Keep the bot log
(`data/logs/bot.log`) open — user-facing errors should always correspond to a
detailed entry there.

## 1. English reel ✅ expected: clean transcript

- [ ] Send a public English-speaking reel (talking-head style, minimal music).
- [ ] Status message advances: `⬇️ Downloading…` → `🎧 Extracting audio…` →
      `✍️ Transcribing…` → `✅ Done — English (en) • ⏱ 0:xx • N words`.
- [ ] A `.md` document arrives, filename `YYYY-MM-DD_<author>_<8hex>.md`.
- [ ] Inline preview appears (transcript < 3500 chars).
- [ ] Open the note in Obsidian: frontmatter parses (no YAML errors), the
      `**Video:**` link opens the reel, `[mm:ss]` markers present.

## 2. Hindi reel ✅ expected: Devanagari or clean romanization

- [ ] Send a public Hindi-only reel.
- [ ] Done message reports `Hindi (hi)`.
- [ ] With `SCRIPT_MODE=native` (or per-user `/settings` → Script: Native):
      transcript is Devanagari with no mojibake (देवनागरी renders correctly).
- [ ] Switch to Script: Roman, send a **different** Hindi reel (cache!) and
      confirm the roman prompt biases output to Roman script.

## 3. Hinglish reel ⚠️ expected: mostly roman, some drift

- [ ] Send a Hindi-English code-switched reel (typical influencer content).
- [ ] Transcript is predominantly Roman script; some segments may still come
      out Devanagari — this is a known Whisper limitation, not a bug. Note the
      ratio; if it's unusable, try `WHISPER_MODEL_NAME=large-v3` (non-turbo).
- [ ] No repetition loops ("...thank you for watching thank you for watching…").

## 4. Private / deleted link ✅ expected: friendly error

- [ ] Send a link to a private account's reel (or a deleted post).
- [ ] Reply is `🔒 This post is private, deleted or otherwise unavailable.`
- [ ] Without cookies, most "private" errors appear as the 🔐 login-required
      message instead — both are correct behaviour.

## 5. Long video ✅ expected: rejected before download

- [ ] Send an Instagram video longer than `MAX_DURATION_SECONDS` (default 20
      min, e.g. an IGTV/long reel).
- [ ] Reply is `⏱ Video is too long (mm:ss — limit is 20:00)` and **no bytes
      were downloaded** (check `data/tmp/` stays empty).
- [ ] Status message shows the error instead of hanging.

## 6. Music-only video ✅ expected: no hallucinated speech

- [ ] Send a reel that is music/edit with no speech (or a story with a song).
- [ ] Expected: either `🤫 No speech detected in this audio.` or a transcript
      containing only the sparse real vocals — **not** the classic
      "Thank you for watching… [MUSIC] [MUSIC]…" hallucination loop.
- [ ] If hallucinations appear: confirm `WHISPER_VAD=true` and
      `WHISPER_MAX_CONTEXT=0` are set, then restart.

## General checks (any of the above runs)

- [ ] Same link a second time → `⚡ Cached — …` reply in ~1–2 s, no
      re-transcription (no `whisper-cli` line in the log).
- [ ] Two different links in one message → both processed, both delivered.
- [ ] `/status` shows correct queue/counter numbers.
- [ ] `/settings` toggles persist across a bot restart (SQLite).
- [ ] `/cancel` while a job runs → status message becomes `🚫 Cancelled.`, no
      leftover files in `data/tmp/`.
- [ ] Non-Instagram link (YouTube) → bot explains what it accepts.
- [ ] `Ctrl+C` during a transcription → clean shutdown log lines, no traceback,
      temp dir purged on next start.
- [ ] `curl 127.0.0.1:8080/health` returns JSON with uptime and counters.
- [ ] Send the same link from a user **not** in `ALLOWED_USER_IDS` → `⛔` reply.
