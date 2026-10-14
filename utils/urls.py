"""Instagram URL extraction and normalization.

Extracts Instagram video links (reel / p / tv / share / stories) from arbitrary
message text and canonicalizes them so they can be used as stable cache keys.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

_KNOWN_HOSTS = {
    "instagram.com",
    "www.instagram.com",
    "m.instagram.com",
    "instagr.am",
    "www.instagr.am",
}

# Scheme is optional so a bare "instagram.com/reel/<code>" in text still matches.
# Path segments may contain letters, digits, underscore, dot and dash; share and
# stories links have several segments (e.g. /share/reel/<id>, /stories/<user>/<id>).
_INSTAGRAM_URL_RE = re.compile(
    r"(?P<url>(?:https?://)?(?:[\w-]+\.)*(?:instagram\.com|instagr\.am)"
    r"/(?:reel|reels|p|tv|share|stories)(?:/[A-Za-z0-9_.-]+)+/?)",
    re.IGNORECASE,
)

# Sentence punctuation that often trails a link pasted into prose.
_TRAILING_PUNCT = ".,;:!?)('\"\u201d\u2019`>"


def normalize_instagram_url(url: str) -> str | None:
    """Return the canonical https://www.instagram.com/... form, or None if not a
    recognized Instagram video URL. Query strings and tracking params are dropped."""
    try:
        parts = urlsplit(url if "://" in url else f"https://{url}")
    except ValueError:
        return None
    if (parts.netloc or "").lower() not in _KNOWN_HOSTS:
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


def extract_instagram_urls(text: str | None) -> list[str]:
    """Extract unique, normalized Instagram video URLs from arbitrary text.

    Returns a de-duplicated list preserving order of first appearance.
    """
    if not text:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for match in _INSTAGRAM_URL_RE.finditer(text):
        raw = match.group("url").rstrip(_TRAILING_PUNCT)
        normalized = normalize_instagram_url(raw)
        if normalized and normalized not in seen:
            seen.add(normalized)
            out.append(normalized)
    return out
