"""Video download via the yt-dlp Python API (run in a worker thread).

Downloads best audio-only when available, otherwise the lowest-resolution
video (we only need the audio track). Enforces duration/size limits before and
during the download, and maps yt-dlp failures to friendly user-facing errors.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Callable
import urllib.request

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from utils.text import format_timestamp

if TYPE_CHECKING:  # pragma: no cover
    from core.config import Settings

log = logging.getLogger(__name__)

# best audio-only → worst combined stream that actually has audio →
# worst video merged with best audio → whatever exists.
_FORMAT_SELECTOR = "best[ext=mp4]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"

_MEDIA_EXTENSIONS = {
    ".mp4", ".mkv", ".webm", ".m4a", ".mp3", ".aac", ".opus", ".mov", ".ogg", ".wav",
}


class Kind:
    PRIVATE = "private"
    LOGIN_REQUIRED = "login_required"
    GEO_RESTRICTED = "geo_restricted"
    TOO_LONG = "too_long"
    TOO_LARGE = "too_large"
    NO_VIDEO = "no_video"
    LIVE = "live"
    EXTRACT_FAILED = "extract_failed"


_FRIENDLY = {
    Kind.PRIVATE: "🔒 This post is private, deleted or otherwise unavailable.",
    Kind.LOGIN_REQUIRED: (
        "🔐 Instagram requires a login for this content — the bot's cookies are "
        "missing or expired. Ask the bot owner to re-export cookies.txt "
        "(see README → Cookies)."
    ),
    Kind.GEO_RESTRICTED: "🌍 This content is geo- or age-restricted in the bot's region.",
    Kind.TOO_LONG: "⏱ Video is too long ({duration} — limit is {limit}).",
    Kind.TOO_LARGE: "📦 Video file is too large{limit}.",
    Kind.NO_VIDEO: "🚫 No downloadable video or photo found at this link.",
    Kind.LIVE: "🔴 Live streams are not supported.",
    Kind.EXTRACT_FAILED: "💥 yt-dlp could not process this link ({reason}). Try again later or update yt-dlp.",
}


class DownloadFailure(Exception):
    """Download failure with a friendly, user-facing message."""

    def __init__(self, kind: str, user_message: str):
        super().__init__(user_message)
        self.kind = kind
        self.user_message = user_message


def _fail(kind: str, **fmt) -> DownloadFailure:
    if kind == Kind.TOO_LARGE:
        limit = fmt.get("limit")
        fmt["limit"] = f" (limit is {limit} MB)" if limit else ""
    return DownloadFailure(kind, _FRIENDLY[kind].format(**fmt))


@dataclass(slots=True)
class DownloadResult:
    filepath: Path | None
    author: str
    title: str
    caption: str
    upload_date: date | None
    duration_s: int
    webpage_url: str
    is_photo_only: bool = False
    photo_paths: list[Path] = field(default_factory=list)


def _classify(exc: BaseException) -> DownloadFailure:
    """Map a yt-dlp exception to a friendly DownloadFailure."""
    msg = str(exc).lower()
    if "max-filesize" in msg or "larger than max" in msg:
        return _fail(Kind.TOO_LARGE, limit="")
    if "private" in msg or "unavailable" in msg or "deleted" in msg:
        return _fail(Kind.PRIVATE)
    if any(
        token in msg
        for token in ("login", "log in", "authenticate", "cookies", "credentials")
    ):
        return _fail(Kind.LOGIN_REQUIRED)
    if any(token in msg for token in ("not available in your country", "geo-restricted", "geographically")):
        return _fail(Kind.GEO_RESTRICTED)
    if ("age" in msg and any(t in msg for t in ("confirm", "restrict", "inappropriate"))) or "age-restricted" in msg:
        return _fail(Kind.GEO_RESTRICTED)
    if any(token in msg for token in ("no video formats", "no formats", "no media", "unsupported url", "does not have")):
        return _fail(Kind.NO_VIDEO)
    if any(token in msg for token in ("404", "page not found", "not found", "http error 5", "http error 4")):
        return _fail(Kind.PRIVATE)
    return _fail(Kind.EXTRACT_FAILED, reason=str(exc)[:200])


def _pick_video_entry(info: dict) -> dict | None:
    """If yt-dlp returned a playlist/carousel, pick the first entry with media."""
    if not info:
        return None
    if info.get("_type") != "playlist":
        return info
    entries = [e for e in (info.get("entries") or []) if e]
    if not entries:
        return None
    with_media = [e for e in entries if e.get("formats") or e.get("duration")]
    return (with_media or entries)[0]


def _has_video_stream(info: dict) -> bool:
    """Check if info or any of its entries contain video formats."""
    if not info:
        return False
    if info.get("_type") == "playlist" or info.get("entries"):
        for e in info.get("entries") or []:
            if e and (e.get("formats") or e.get("duration")):
                for f in e.get("formats") or []:
                    if f.get("vcodec") and f.get("vcodec") != "none":
                        return True
                if e.get("duration"):
                    return True
        return False
    for f in info.get("formats") or []:
        if f.get("vcodec") and f.get("vcodec") != "none":
            return True
    return bool(info.get("duration"))


def _extract_image_urls(info: dict) -> list[str]:
    """Extract ordered high-resolution image URLs from a photo or carousel post."""
    urls: list[str] = []
    if info.get("_type") == "playlist" or info.get("entries"):
        for e in info.get("entries") or []:
            if not e:
                continue
            thumbs = e.get("thumbnails") or []
            if thumbs:
                best = max(
                    thumbs,
                    key=lambda t: (t.get("width") or 0) * (t.get("height") or 0) or len(t.get("url") or ""),
                )
                if best.get("url"):
                    urls.append(best["url"])
                    continue
            if e.get("url") and not e.get("formats"):
                urls.append(e["url"])
    else:
        thumbs = info.get("thumbnails") or []
        if thumbs:
            best = max(
                thumbs,
                key=lambda t: (t.get("width") or 0) * (t.get("height") or 0) or len(t.get("url") or ""),
            )
            if best.get("url"):
                urls.append(best["url"])
        elif info.get("url"):
            urls.append(info["url"])
    return urls


def _download_photos_sync(urls: list[str], tmp_dir: Path) -> list[Path]:
    """Download images in order in HD resolution."""
    downloaded: list[Path] = []
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    for idx, u in enumerate(urls):
        dest = tmp_dir / f"photo_{idx:02d}.jpg"
        try:
            req = urllib.request.Request(u, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as resp, open(dest, "wb") as out:
                out.write(resp.read())
            if dest.is_file() and dest.stat().st_size > 0:
                downloaded.append(dest)
        except Exception:
            log.warning("could not download image %s", u, exc_info=True)
    return downloaded


def _download_sync(
    url: str,
    tmp_dir: Path,
    settings: "Settings",
    progress: Callable[[int], None] | None,
) -> DownloadResult:
    cookies = Path(settings.cookies_file) if settings.cookies_file else None
    if cookies is not None and not cookies.is_file():
        log.warning("COOKIES_FILE is set but %s does not exist; continuing without cookies", cookies)
        cookies = None

    common: dict = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "socket_timeout": 30,
        "retries": 3,
        "extractor_retries": 2,
    }
    if cookies is not None:
        common["cookiefile"] = str(cookies)

    # Pass 1: metadata only — enforce limits before transferring any bytes.
    with YoutubeDL(dict(common)) as ydl:
        try:
            raw_info = ydl.extract_info(url, download=False)
        except DownloadError as exc:
            raise _classify(exc) from exc

    if not _has_video_stream(raw_info):
        image_urls = _extract_image_urls(raw_info or {})
        if image_urls:
            photos = _download_photos_sync(image_urls, tmp_dir)
            if photos:
                info = _pick_video_entry(raw_info or {}) or {}
                raw_date = info.get("upload_date")
                upload_date = None
                if raw_date:
                    try:
                        upload_date = datetime.strptime(str(raw_date), "%Y%m%d").date()
                    except ValueError:
                        upload_date = None
                return DownloadResult(
                    filepath=None,
                    author=str(info.get("uploader") or info.get("channel") or info.get("uploader_id") or ""),
                    title=str(info.get("title") or ""),
                    caption=str(info.get("description") or ""),
                    upload_date=upload_date,
                    duration_s=0,
                    webpage_url=str(info.get("webpage_url") or url),
                    is_photo_only=True,
                    photo_paths=photos,
                )

    info = _pick_video_entry(raw_info or {})
    if not info:
        raise _fail(Kind.NO_VIDEO)
    if info.get("is_live"):
        raise _fail(Kind.LIVE)
    duration = info.get("duration")
    if isinstance(duration, (int, float)) and duration > settings.max_duration_seconds:
        raise _fail(
            Kind.TOO_LONG,
            duration=format_timestamp(duration),
            limit=format_timestamp(settings.max_duration_seconds),
        )
    filesize = info.get("filesize") or info.get("filesize_approx") or 0
    if isinstance(filesize, (int, float)) and filesize > settings.max_filesize_bytes:
        raise _fail(Kind.TOO_LARGE, limit=settings.max_filesize_mb)

    hooks = []
    if progress is not None:
        last = {"pct": None}
        ansi = re.compile(r"\x1b\[[0-9;]*m")

        def hook(d):
            if d.get("status") != "downloading":
                return
            done = d.get("downloaded_bytes")
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if isinstance(done, (int, float)) and isinstance(total, (int, float)) and total > 0:
                pct = int(done * 100 / total)
            else:
                # _percent_str may carry ANSI colour escapes
                raw = ansi.sub("", str(d.get("_percent_str") or "")).strip().rstrip("%").strip()
                try:
                    pct = int(float(raw))
                except ValueError:
                    return
            if pct != last["pct"]:
                last["pct"] = pct
                progress(pct)

        hooks.append(hook)

    opts = dict(common)
    opts.update(
        {
            "format": _FORMAT_SELECTOR,
            "outtmpl": str(tmp_dir / "%(id)s.%(ext)s"),
            "max_filesize": settings.max_filesize_bytes,
            "noplaylist": True,
            "concurrent_fragment_downloads": 2,
            "buffersize": 1024 * 64,
            "progress_hooks": hooks,
        }
    )
    # Pass 2: the actual download.
    with YoutubeDL(opts) as ydl:
        try:
            info = ydl.extract_info(url, download=True)
        except DownloadError as exc:
            raise _classify(exc) from exc
    info = _pick_video_entry(info or {})
    if not info:
        raise _fail(Kind.NO_VIDEO)

    path: Path | None = None
    for requested in info.get("requested_downloads") or []:
        filepath = requested.get("filepath")
        if filepath and Path(filepath).is_file():
            path = Path(filepath)
            break
    if path is None:
        # Fallback: newest media-looking file in the temp dir (skips .part files).
        candidates = [
            p
            for p in tmp_dir.iterdir()
            if p.is_file() and p.suffix.lower() in _MEDIA_EXTENSIONS and not p.name.endswith(".part")
        ]
        if candidates:
            path = max(candidates, key=lambda p: p.stat().st_mtime)
    if path is None:
        raise _fail(Kind.NO_VIDEO)

    upload_date = None
    raw_date = info.get("upload_date")
    if raw_date:
        try:
            upload_date = datetime.strptime(str(raw_date), "%Y%m%d").date()
        except ValueError:
            upload_date = None

    final_duration = duration if isinstance(duration, (int, float)) else info.get("duration") or 0
    return DownloadResult(
        filepath=path,
        author=str(info.get("uploader") or info.get("channel") or info.get("uploader_id") or ""),
        title=str(info.get("title") or ""),
        caption=str(info.get("description") or ""),
        upload_date=upload_date,
        duration_s=int(final_duration or 0),
        webpage_url=str(info.get("webpage_url") or url),
    )


async def download_video(
    url: str,
    tmp_dir: Path,
    *,
    settings: "Settings",
    progress: Callable[[int], None] | None = None,
) -> DownloadResult:
    """Async wrapper: run the blocking yt-dlp work in a thread, forwarding
    download progress to ``progress`` on the event loop."""
    loop = asyncio.get_running_loop()

    def threadsafe_progress(pct: int) -> None:
        if progress is not None:
            loop.call_soon_threadsafe(progress, pct)

    return await asyncio.to_thread(
        _download_sync,
        url,
        Path(tmp_dir),
        settings,
        threadsafe_progress if progress is not None else None,
    )
