"""AI Summarization service (Google Gemini & OpenAI-compatible providers)."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from core.config import Settings
    from services.markdown import VideoMeta

log = logging.getLogger("summarizer")

SYSTEM_PROMPT = """You are an expert audio transcription editor, linguist, and senior research assistant specializing in synthesizing video transcripts into world-class Obsidian notes.

Your job has TWO parts:

PART 1: TRANSCRIPT RESTORATION & CLEANUP
- The raw transcript was produced by Whisper ASR and transliteration and often contains severe phonetic distortions or transliteration artifacts, especially for Romanized Hinglish / Hindi / Urdu speech (e.g. 'andin jnzi' -> 'Indian Gen-Z', 'alikshn kmishn' -> 'Election Commission', 'rizaئn' -> 'resign', 'protist' -> 'protest', 'kijoaliti' -> 'casualty', 'aidokishn mnstr' -> 'Education Minister', 'pi ti aayi' -> 'PTI', 'ti lpi' -> 'TLP', 'di chok' -> 'D-Chowk', 'stodns' -> 'students', 'aafisr' -> 'officer', 'praئm mnstr' -> 'Prime Minister', 'chif mnstr' -> 'Chief Minister').
- Clean and restore the transcript into natural, fluent, accurately spelled text. If it is Roman Hinglish, write natural Roman Hinglish with proper English words. If it is English, fix any minor speech recognition mishearings.
- CRITICAL: Keep all timestamp markers like [0:00], [1:44], [2:50] intact and in place!
- Do not omit or summarize the transcript in Part 1; restore the full text line by line.

PART 2: OBSIDIAN EXECUTIVE SUMMARY & COMPREHENSIVE KNOWLEDGE SYNTHESIS
Format the summary strictly for an Obsidian Knowledge Base / Lifebook vault. Use native Obsidian Markdown callouts and wikilinks:

1. Executive Summary Callout (CRITICAL: MUST BE THE FIRST ELEMENT IN THE SUMMARY):
> [!summary] Executive Summary
> (2-4 concise, high-density sentences summarizing the core argument, thesis, or narrative of the video)

2. Key Claims & Core Ideas:
### 💡 Key Claims & Core Ideas
- Bullet points distilling the speaker's main propositions, core arguments, and philosophical or technical flow.

3. Key Books, References & Literature:
### 📚 Key Books, References & Literature
- **Explicit References**: If any books, authors, papers, studies, or thinkers were mentioned or cited in the video, list them with author name and specific context.
- **Recommended Reading**: Recommend 1-2 foundational, authoritative books or seminal literature that expand directly on the concepts, psychology, business, or framework discussed in the video.
- Format book titles and authors with Obsidian wikilinks: e.g. *[[Book Title]]* by [[Author Name]] — followed by a concise 1-2 sentence explanation of how its core thesis connects to this video.

4. Key Facts, Data & Evidence:
### 📊 Key Facts, Data & Evidence
- Concrete bullet points highlighting specific numbers, percentages, data points, verified facts, scientific / biological principles, historical milestones, laws, or company case studies mentioned or underlying the claims.

5. Mental Models & Conceptual Frameworks:
### 🧠 Mental Models & Frameworks
- Identify and link key mental models, cognitive biases, or conceptual frameworks at play (e.g. `[[First Principles Thinking]]`, `[[Pareto Principle]]`, `[[Compounding]]`, `[[Inversion]]`, `[[Opportunity Cost]]`, etc.).

6. Actionable Takeaways & Next Steps:
> [!tip] Actionable Takeaways
> - Action-oriented bullet points outlining concrete habits, systems, or rules the viewer can apply immediately in their life or work.

7. Related Topics & Tags:
### 🏷️ Related Concepts & Tags
- Wikilinks to related Obsidian subject notes (e.g. `[[Productivity]]`, `[[Psychology]]`, `[[Finance]]`, `[[Decision Making]]`) and relevant topic hashtags (e.g. `#reels #knowledge #summary`).

OUTPUT FORMAT:
You MUST format your output strictly with the following delimiters so automated parsers can extract them:

===CLEANED_TRANSCRIPT===
(the restored, cleaned transcript preserving all timestamp markers)
===SUMMARY===
(the obsidian markdown summary starting with > [!summary] Executive Summary)
"""

USER_PROMPT_TEMPLATE = """Video Metadata:
- Title: {title}
- Author/Creator: {author}
- Duration: {duration}
- Detected Language: {language}

Transcript:
{transcript}

Please restore the transcript (preserving all timestamp markers) and generate the comprehensive Obsidian summary including key book references, facts, and actionable takeaways formatted for Obsidian notes as instructed."""


class SummarizerResult(str):
    """Backwards-compatible string subclass holding both summary markdown and restored transcript."""

    summary_markdown: str
    cleaned_transcript: str | None

    def __new__(cls, summary_markdown: str, cleaned_transcript: str | None = None):
        obj = super().__new__(cls, summary_markdown)
        obj.summary_markdown = summary_markdown
        obj.cleaned_transcript = cleaned_transcript
        return obj


@dataclass
class SummarizerStats:
    configured: bool = False
    provider: str = "none"
    model: str = ""
    last_status: str = "not_configured"  # not_configured | ok | error | skipped
    last_error: str | None = None
    last_request_at: str | None = None
    success_count: int = 0
    error_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "configured": self.configured,
            "provider": self.provider,
            "model": self.model or None,
            "last_status": self.last_status,
            "last_error": self.last_error,
            "last_request_at": self.last_request_at,
            "success_count": self.success_count,
            "error_count": self.error_count,
        }


class Summarizer:
    """Orchestrates AI summarization & transcript restoration with robust fallback and health monitoring."""

    def __init__(self, settings: "Settings"):
        self._settings = settings
        self.stats_data = SummarizerStats()
        self._refresh_config()

    def _refresh_config(self) -> None:
        key = self._settings.effective_llm_api_key
        if not key:
            self.stats_data.configured = False
            self.stats_data.provider = "none"
            self.stats_data.model = ""
            if self.stats_data.last_status not in ("ok", "error"):
                self.stats_data.last_status = "not_configured"
        else:
            self.stats_data.configured = True
            self.stats_data.provider = self._settings.effective_llm_provider
            self.stats_data.model = self._settings.effective_llm_model

    @property
    def is_configured(self) -> bool:
        self._refresh_config()
        return self.stats_data.configured

    def stats(self) -> dict[str, Any]:
        self._refresh_config()
        return self.stats_data.to_dict()

    async def summarize(
        self,
        meta: "VideoMeta",
        transcript_text: str,
    ) -> SummarizerResult | None:
        """Generate structured Obsidian summary & cleaned transcript. Returns None if unconfigured or on failure."""
        self._refresh_config()
        if not self.is_configured:
            return None

        clean_transcript = (transcript_text or "").strip()
        if len(clean_transcript) < 20:
            self.stats_data.last_status = "skipped"
            return None

        keys_to_try = getattr(self._settings, "effective_llm_api_keys", None) or [self._settings.effective_llm_api_key]
        keys_to_try = [k for k in keys_to_try if k.strip()]
        if not keys_to_try:
            return None

        base_url = self._settings.effective_llm_base_url
        model = self._settings.effective_llm_model
        provider = self._settings.effective_llm_provider
        timeout = float(self._settings.llm_timeout_seconds or 45)

        self.stats_data.last_request_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

        prompt = USER_PROMPT_TEMPLATE.format(
            title=meta.title or "Instagram video",
            author=meta.author or "Unknown",
            duration=f"{meta.duration_s}s" if meta.duration_s else "unknown",
            language=meta.language or "Unknown",
            transcript=clean_transcript[:25000],  # generous safety token budget
        )

        # Determine model cascade sequence
        if provider == "gemini":
            models_to_try = [
                "gemini-3-flash-preview",
                "gemini-3.1-flash-lite",
                "gemini-2.5-flash",
            ]
            # If user explicitly specified a custom model not in the standard cascade, try it first
            if model and model not in models_to_try and model != "gemini-3-flash":
                models_to_try.insert(0, model)
        else:
            models_to_try = [model]

        last_error_exc: Exception | None = None
        for current_model in models_to_try:
            for acc_idx, current_api_key in enumerate(keys_to_try):
                try:
                    raw_response: str | None = None
                    # 1. Primary path: OpenAI-compatible /chat/completions
                    try:
                        raw_response = await self._call_chat_completions(
                            base_url=base_url,
                            api_key=current_api_key,
                            model=current_model,
                            prompt=prompt,
                            timeout=timeout,
                        )
                    except Exception as first_exc:
                        # If provider is Gemini and OpenAI-compatible endpoint returned 404/405 or non-status error,
                        # fall back to native Google Gemini generateContent REST API
                        should_try_native = (
                            provider == "gemini"
                            and (
                                not isinstance(first_exc, httpx.HTTPStatusError)
                                or first_exc.response.status_code in (404, 405, 501)
                            )
                        )
                        if should_try_native:
                            log.info(
                                "OpenAI endpoint attempt on Gemini failed for %s (%s); trying native Gemini API",
                                current_model,
                                first_exc,
                            )
                            raw_response = await self._call_gemini_native(
                                api_key=current_api_key,
                                model=current_model,
                                prompt=prompt,
                                timeout=timeout,
                            )
                        else:
                            raise first_exc

                    if raw_response and raw_response.strip():
                        parsed = self._parse_response(raw_response)
                        self.stats_data.last_status = "ok"
                        self.stats_data.last_error = None
                        self.stats_data.model = current_model
                        self.stats_data.success_count += 1
                        return parsed
                    else:
                        raise ValueError(f"LLM returned an empty response for {current_model}")

                except Exception as exc:
                    last_error_exc = exc
                    masked_key = current_api_key[:10] + "..." if len(current_api_key) >= 10 else "***"
                    log.warning(
                        "LLM call failed with model %s on account %d (%s): %s; trying next fallback...",
                        current_model,
                        acc_idx + 1,
                        masked_key,
                        exc,
                    )
                    continue

        err_msg = (
            f"{type(last_error_exc).__name__}: {str(last_error_exc)[:250]}"
            if last_error_exc
            else "All model and account fallbacks failed"
        )
        log.warning("All LLM model & account fallbacks failed: %s; skipping summary", err_msg)
        self.stats_data.last_status = "error"
        self.stats_data.last_error = err_msg
        self.stats_data.error_count += 1
        return None

    def _parse_response(self, text: str) -> SummarizerResult:
        text = self._clean_markdown(text)
        cleaned_transcript: str | None = None
        summary_md: str = ""

        if "===CLEANED_TRANSCRIPT===" in text and "===SUMMARY===" in text:
            parts = text.split("===SUMMARY===")
            transcript_part = parts[0].replace("===CLEANED_TRANSCRIPT===", "").strip()
            summary_part = parts[1].strip() if len(parts) > 1 else ""
            if transcript_part:
                cleaned_transcript = transcript_part
            summary_md = summary_part
        elif "===SUMMARY===" in text:
            parts = text.split("===SUMMARY===")
            cleaned_transcript = parts[0].replace("===CLEANED_TRANSCRIPT===", "").strip() or None
            summary_md = parts[1].strip()
        elif "===CLEANED_TRANSCRIPT===" in text:
            cleaned_transcript = text.replace("===CLEANED_TRANSCRIPT===", "").strip() or None
            summary_md = ""
        else:
            # Fallback: if delimiters omitted, check if it's an obsidian summary or transcript
            if "> [!summary]" in text or "## " in text or "**Key " in text:
                summary_md = text
            else:
                cleaned_transcript = text
                summary_md = ""

        return SummarizerResult(
            summary_markdown=summary_md,
            cleaned_transcript=cleaned_transcript,
        )

    async def _call_chat_completions(
        self,
        base_url: str,
        api_key: str,
        model: str,
        prompt: str,
        timeout: float,
    ) -> str | None:
        endpoint = base_url.rstrip("/")
        if not endpoint.endswith("/chat/completions"):
            endpoint = f"{endpoint}/chat/completions"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(endpoint, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices") or []
            if choices:
                msg = choices[0].get("message") or {}
                return msg.get("content", "").strip()
        return None

    async def _call_gemini_native(
        self,
        api_key: str,
        model: str,
        prompt: str,
        timeout: float,
    ) -> str | None:
        """Direct REST call to Google Generative Language API."""
        endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        )
        payload = {
            "system_instruction": {
                "parts": [{"text": SYSTEM_PROMPT}]
            },
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
            },
        }

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(endpoint, json=payload)
            resp.raise_for_status()
            data = resp.json()
            candidates = data.get("candidates") or []
            if candidates:
                content = candidates[0].get("content") or {}
                parts = content.get("parts") or []
                if parts:
                    return parts[0].get("text", "").strip()
        return None

    def _clean_markdown(self, text: str) -> str:
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        return text
