import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path
import httpx
import pytest

from core.config import Settings
from services.markdown import VideoMeta, render_markdown
from services.summarizer import Summarizer


def test_summarizer_unconfigured():
    settings = Settings(
        tg_api_id=1,
        tg_api_hash="hash",
        tg_bot_token="token",
        llm_api_key="",
    )
    summarizer = Summarizer(settings)
    assert not summarizer.is_configured
    stats = summarizer.stats()
    assert stats["configured"] is False
    assert stats["last_status"] == "not_configured"

    meta = VideoMeta(url="https://instagr.am/1", title="Test")
    res = asyncio.run(summarizer.summarize(meta, "Some transcript text here"))
    assert res is None


def test_summarizer_gemini_detection_and_success():
    settings = Settings(
        tg_api_id=1,
        tg_api_hash="hash",
        tg_bot_token="token",
        llm_api_key="AIzaSyDummyGeminiKey",
    )
    assert settings.effective_llm_provider == "gemini"
    assert settings.effective_llm_model == "gemini-3-flash-preview"

    summarizer = Summarizer(settings)
    assert summarizer.is_configured

    mock_resp_data = {
        "choices": [
            {
                "message": {
                    "content": "> [!summary] Executive Summary\n> Great video.\n\n### 💡 Key Claims & Core Arguments\n- **Fast**: Very fast."
                }
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value=mock_resp_data)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        meta = VideoMeta(url="https://instagr.am/1", title="Uber Tech")
        res = asyncio.run(summarizer.summarize(meta, "Driver sends location every four seconds."))

        assert res is not None
        assert "> [!summary] Executive Summary" in res
        assert "Great video." in res

        stats = summarizer.stats()
        assert stats["configured"] is True
        assert stats["last_status"] == "ok"
        assert stats["success_count"] == 1
        assert stats["error_count"] == 0


def test_summarizer_openai_compatible_error_fallback_resilient():
    # Test error-proof fallback: if API returns 401 / error, summarizer returns None without crashing
    settings = Settings(
        tg_api_id=1,
        tg_api_hash="hash",
        tg_bot_token="token",
        llm_api_key="sk-invalid-test-key",
    )
    assert settings.effective_llm_provider == "openai"
    summarizer = Summarizer(settings)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        # Simulate 401 Unauthorized
        req = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
        mock_post.side_effect = httpx.HTTPStatusError("401 Unauthorized", request=req, response=httpx.Response(401, request=req))

        meta = VideoMeta(url="https://instagr.am/1", title="Fail Test")
        res = asyncio.run(summarizer.summarize(meta, "Some real transcript speech text to summarize."))

        # Must return None (skipped), never raise!
        assert res is None

        # Health stats must record the error
        stats = summarizer.stats()
        assert stats["last_status"] == "error"
        assert "HTTPStatusError" in stats["last_error"]
        assert stats["error_count"] == 1
        assert stats["success_count"] == 0


def test_summarizer_gemini_native_fallback():
    # If OpenAI endpoint on Gemini fails, it tries native generateContent endpoint
    settings = Settings(
        tg_api_id=1,
        tg_api_hash="hash",
        tg_bot_token="token",
        gemini_api_key="AIzaSyNativeTest",
    )
    summarizer = Summarizer(settings)

    mock_native_data = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "```markdown\n> [!summary] Executive Summary\n> Native Gemini summary.\n```"}]
                }
            }
        ]
    }

    mock_native_resp = MagicMock()
    mock_native_resp.raise_for_status = MagicMock()
    mock_native_resp.json = MagicMock(return_value=mock_native_data)

    # First call (OpenAI) raises, second call (native) succeeds
    req = httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions")
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = [
            httpx.HTTPStatusError("404 Not Found", request=req, response=httpx.Response(404, request=req)),
            mock_native_resp,
        ]

        meta = VideoMeta(url="https://instagr.am/1", title="Uber Tech")
        res = asyncio.run(summarizer.summarize(meta, "Audio transcript with enough words."))

        assert res is not None
        # Checks markdown backticks got cleaned
        assert not res.startswith("```")
        assert "> [!summary] Executive Summary" in res
        assert "Native Gemini summary." in res


def test_markdown_with_summary_structure():
    meta = VideoMeta(
        url="https://instagr.am/1",
        title="AI in Healthcare",
        duration_s=60,
        language="en",
    )
    summary_md = (
        "> [!summary] Executive Summary\n"
        "> AI helps diagnose illnesses earlier.\n\n"
        "### 💡 Key Claims & Core Arguments\n"
        "- **Speed**: 10x faster imaging analysis.\n\n"
        "### 🔍 Key Facts, Figures & Details\n"
        "- **Accuracy**: 99.2% accuracy reported."
    )

    md = render_markdown(meta, "Full transcript here.", summary_markdown=summary_md)
    assert "## 📌 AI Summary & Analysis" in md
    assert "> [!summary] Executive Summary" in md
    assert "### 💡 Key Claims & Core Arguments" in md
    assert "### 🔍 Key Facts, Figures & Details" in md
    assert "tags: [transcript, instagram, summary]" in md
    assert "## Transcript" in md


def test_summarizer_dual_output_parsing():
    settings = Settings(
        tg_api_id=1,
        tg_api_hash="hash",
        tg_bot_token="token",
        llm_api_key="AQ.DummyKey",
    )
    summarizer = Summarizer(settings)

    mock_payload = (
        "===CLEANED_TRANSCRIPT===\n"
        "[0:00] Indian Gen-Z toh phir se nikal aaye.\n\n"
        "===SUMMARY===\n"
        "> [!summary] Executive Summary\n"
        "> High quality summary.\n\n"
        "* Key point 1"
    )
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"choices": [{"message": {"content": mock_payload}}]})

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        meta = VideoMeta(url="https://instagr.am/1", title="Test")
        res = asyncio.run(summarizer.summarize(meta, "Raw speech transcript here"))

        assert res is not None
        assert res.cleaned_transcript == "[0:00] Indian Gen-Z toh phir se nikal aaye."
        assert "> [!summary] Executive Summary" in res.summary_markdown
        # Backwards compatible string check
        assert "> [!summary] Executive Summary" in res


def test_summarizer_fallback_key_on_exhaustion():
    settings = Settings(
        tg_api_id=1,
        tg_api_hash="hash",
        tg_bot_token="token",
        llm_api_key="sk-primary-exhausted",
        llm_fallback_api_key="sk-working-fallback",
    )
    summarizer = Summarizer(settings)
    assert "sk-primary-exhausted" in settings.effective_llm_api_keys
    assert "sk-working-fallback" in settings.effective_llm_api_keys

    # First call (primary key) raises 429 Too Many Requests; second call (fallback key) succeeds
    req = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    err_429 = httpx.HTTPStatusError("429 Quota Exhausted", request=req, response=httpx.Response(429, request=req))

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"choices": [{"message": {"content": "> [!summary] Executive Summary\n> Success with fallback."}}]})

    calls = []
    async def mock_post(*args, **kwargs):
        headers = kwargs.get("headers", {})
        calls.append(headers.get("Authorization"))
        if len(calls) == 1:
            raise err_429
        return mock_resp

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        meta = VideoMeta(url="https://instagr.am/1", title="Failover Test")
        res = asyncio.run(summarizer.summarize(meta, "Test speech transcript that needs fallback key"))

        assert res is not None
        assert "Success with fallback." in res
        assert summarizer.stats()["success_count"] == 1
        assert "Bearer sk-primary-exhausted" in calls[0]
        assert "Bearer sk-working-fallback" in calls[1]


def test_mac_hardware_optimization_concurrency():
    s_mac = Settings(
        tg_api_id=1,
        tg_api_hash="hash",
        tg_bot_token="token",
        on_mac=True,
    )
    assert s_mac.effective_worker_concurrency == 3
    assert s_mac.effective_download_concurrency == 4
    assert s_mac.effective_threads >= 2

    s_vps = Settings(
        tg_api_id=1,
        tg_api_hash="hash",
        tg_bot_token="token",
        on_mac=False,
        is_mac=False,
        worker_concurrency=1,
        download_concurrency=2,
    )
    assert s_vps.effective_worker_concurrency == 1
    assert s_vps.effective_download_concurrency == 2


def test_summarizer_gemini_cascade_order():
    settings = Settings(
        tg_api_id=1,
        tg_api_hash="hash",
        tg_bot_token="token",
        llm_api_key="AIzaSyPrimaryAccount",
        llm_fallback_api_key="AIzaSyBackupAccount",
        _env_file=None,
    )
    summarizer = Summarizer(settings)

    calls = []
    req = httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions")
    err_503 = httpx.HTTPStatusError("503 Overloaded", request=req, response=httpx.Response(503, request=req))

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={
        "choices": [{"message": {"content": "> [!summary] Executive Summary\n> Finally succeeded on stage 5."}}]
    })

    async def mock_post(*args, **kwargs):
        json_data = kwargs.get("json", {})
        headers = kwargs.get("headers", {})
        model = json_data.get("model")
        auth = headers.get("Authorization")
        calls.append((model, auth))
        # Fail the first 4 attempts, succeed on the 5th (gemini-2.5-flash on primary account)
        if len(calls) < 5:
            raise err_503
        return mock_resp

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        meta = VideoMeta(url="https://instagr.am/1", title="Cascade Test")
        res = asyncio.run(summarizer.summarize(meta, "A long speech transcript to trigger summarizer."))

        assert res is not None
        assert "Finally succeeded on stage 5." in res
        # Check exact sequence of calls:
        # 1. gemini-3-flash-preview on account 1
        # 2. gemini-3-flash-preview on account 2
        # 3. gemini-3.1-flash-lite on account 1
        # 4. gemini-3.1-flash-lite on account 2
        # 5. gemini-2.5-flash on account 1
        assert len(calls) == 5
        assert calls[0] == ("gemini-3-flash-preview", "Bearer AIzaSyPrimaryAccount")
        assert calls[1] == ("gemini-3-flash-preview", "Bearer AIzaSyBackupAccount")
        assert calls[2] == ("gemini-3.1-flash-lite", "Bearer AIzaSyPrimaryAccount")
        assert calls[3] == ("gemini-3.1-flash-lite", "Bearer AIzaSyBackupAccount")
        assert calls[4] == ("gemini-2.5-flash", "Bearer AIzaSyPrimaryAccount")

