"""Instagram and YouTube URL extraction and normalization.

Extracts video links (Instagram reel / p / tv / share / stories and YouTube Shorts)
from arbitrary message text and canonicalizes them so they can be used as stable cache keys.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

_INSTAGRAM_HOSTS = {
    "instagram.com",
    "www.instagram.com",
    "m.instagram.com",
    "instagr.am",
    "www.instagr.am",
}
_KNOWN_HOSTS = _INSTAGRAM_HOSTS

_YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "www.youtu.be",
}

# Scheme is optional so bare links in text still match.
_INSTAGRAM_URL_RE = re.compile(
    r"(?P<url>(?:https?://)?(?:[\w-]+\.)*(?:instagram\.com|instagr\.am)"
    r"/(?:reel|reels|p|tv|share|stories)(?:/[A-Za-z0-9_.-]+)+/?)",
    re.IGNORECASE,
)

_YOUTUBE_URL_RE = re.compile(
    r"(?P<url>(?:https?://)?(?:(?:[\w-]+\.)*youtube\.com/(?:shorts/|watch\?(?:[^\s&]*&)*v=)|youtu\.be/)[A-Za-z0-9_-]{11}[^\s]*)",
    re.IGNORECASE,
)

_YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

# Sentence punctuation that often trails a link pasted into prose.
_TRAILING_PUNCT = ".,;:!?)('\"\u201d\u2019`>"


def is_instagram_url(url: str) -> bool:
    """Return True if the URL host belongs to Instagram."""
    try:
        parts = urlsplit(url if "://" in url else f"https://{url}")
        return (parts.netloc or "").lower() in _INSTAGRAM_HOSTS
    except ValueError:
        return False


def is_youtube_url(url: str) -> bool:
    """Return True if the URL host belongs to YouTube."""
    try:
        parts = urlsplit(url if "://" in url else f"https://{url}")
        return (parts.netloc or "").lower() in _YOUTUBE_HOSTS
    except ValueError:
        return False


def normalize_instagram_url(url: str) -> str | None:
    """Return the canonical https://www.instagram.com/... form, or None if not a
    recognized Instagram video URL. Query strings and tracking params are dropped."""
    try:
        parts = urlsplit(url if "://" in url else f"https://{url}")
    except ValueError:
        return None
    if (parts.netloc or "").lower() not in _INSTAGRAM_HOSTS:
        return None
    segments = [s for s in parts.path.split("/") if s]
    if not segments:
        return None
    kind = segments[0].lower()
    if kind in ("reel", "reels", "p", "tv"):
        if len(segments) < 2:
            return None
        canonical_kind = "reel" if kind in ("reel", "reels") else kind
        return f"https://www.instagram.com/{canonical_kind}/{segments[1]}/"
    if kind == "share":
        # Share links (instagram.com/share/reel/<id>) resolve via redirect; keep
        # the full sub-path so yt-dlp can follow it.
        if len(segments) < 2:
            return None
        return "https://www.instagram.com/share/" + "/".join(segments[1:]) + "/"
    if kind == "stories":
        if len(segments) < 3:  # stories/<username>/<media_id>
            return None
        return "https://www.instagram.com/stories/" + "/".join(segments[1:3]) + "/"
    return None


def normalize_youtube_url(url: str) -> str | None:
    """Return canonical https://www.youtube.com/shorts/<video_id> form, or None if
    not a recognized YouTube video/shorts URL. Tracking queries are dropped."""
    try:
        parts = urlsplit(url if "://" in url else f"https://{url}")
    except ValueError:
        return None
    netloc = (parts.netloc or "").lower()
    if netloc not in _YOUTUBE_HOSTS:
        return None

    video_id: str | None = None
    if netloc in ("youtu.be", "www.youtu.be"):
        segments = [s for s in parts.path.split("/") if s]
        if segments:
            video_id = segments[0]
    else:
        segments = [s for s in parts.path.split("/") if s]
        if not segments:
            return None
        kind = segments[0].lower()
        if kind == "shorts" and len(segments) >= 2:
            video_id = segments[1]
        elif kind == "watch":
            qs = parse_qs(parts.query)
            v_list = qs.get("v")
            if v_list:
                video_id = v_list[0]

    if not video_id or not _YOUTUBE_ID_RE.match(video_id):
        return None
    return f"https://www.youtube.com/shorts/{video_id}"


def normalize_url(url: str) -> str | None:
    """Normalize either an Instagram video URL or a YouTube Shorts URL to canonical form."""
    return normalize_instagram_url(url) or normalize_youtube_url(url)


def extract_urls(text: str | None) -> list[str]:
    """Extract unique, normalized Instagram and YouTube Shorts URLs from arbitrary text.

    Returns a de-duplicated list preserving order of first appearance.
    """
    if not text:
        return []
    matches: list[tuple[int, str]] = []
    for match in _INSTAGRAM_URL_RE.finditer(text):
        raw = match.group("url").rstrip(_TRAILING_PUNCT)
        matches.append((match.start(), raw))
    for match in _YOUTUBE_URL_RE.finditer(text):
        raw = match.group("url").rstrip(_TRAILING_PUNCT)
        matches.append((match.start(), raw))
    matches.sort(key=lambda x: x[0])

    seen: set[str] = set()
    out: list[str] = []
    for _, raw in matches:
        normalized = normalize_url(raw)
        if normalized and normalized not in seen:
            seen.add(normalized)
            out.append(normalized)
    return out


# Backward compatibility alias
extract_instagram_urls = extract_urls

