"""Transcript post-processing.

Turns raw whisper segments into readable text: strip [MUSIC]-style tags,
collapse consecutive repeated-line hallucinations, group into paragraphs and
insert sparse [mm:ss] timestamp markers.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Whisper bracket/parenthesis audio tags: [MUSIC], (music), [BLANK_AUDIO],
# [SILENCE], [APPLAUSE], [CHEERING], [LAUGHTER] and spacing/separator variants.
_AUDIO_TAGS_RE = re.compile(
    r"[\[(]\s*(?:music|blank[_\s-]?audio|silence|applause|cheering|crowd"
    r"|laughter|laughing)\s*[\])]",
    re.IGNORECASE,
)

_SENTENCE_END = ".!?।"


@dataclass(slots=True)
class Segment:
    """One timestamped chunk of speech as produced by the transcriber."""

    start: float
    end: float
    text: str


@dataclass(slots=True)
class Paragraph:
    text: str
    start: float


def _norm_for_compare(s: str) -> str:
    """Normalize text for duplicate comparison: keep only word chars, lowercase."""
    return re.sub(r"[^\w]", "", s, flags=re.UNICODE).casefold()


def clean_segments(
    segments: list[Segment],
    *,
    keep_tags: bool = False,
    to_roman: bool = False,
) -> list[Segment]:
    """Clean whisper output segments.

    - Strips [MUSIC]-style tags (unless keep_tags).
    - Trims whitespace and dangling dashes.
    - If to_roman is True, converts Urdu and Devanagari script to Roman Hinglish.
    - Collapses *consecutive* duplicate segments — the classic whisper
      hallucination loop ("Thank you for watching" × N) keeps only the first.
    """
    from utils.hinglish import to_hinglish

    out: list[Segment] = []
    last_cmp: str | None = None
    for seg in segments:
        text = " ".join((seg.text or "").split())
        if not keep_tags:
            text = _AUDIO_TAGS_RE.sub(" ", text)
            text = " ".join(text.split())
        text = text.strip(" -–—")
        if not text:
            continue
        if to_roman:
            text = to_hinglish(text)
        cmp_key = _norm_for_compare(text)
        if cmp_key and cmp_key == last_cmp:
            continue
        out.append(Segment(seg.start, seg.end, text))
        last_cmp = cmp_key
    return out


def build_paragraphs(
    segments: list[Segment],
    *,
    max_gap_s: float = 2.0,
    target_chars: int = 320,
    min_chars: int = 60,
) -> list[Paragraph]:
    """Group segments into paragraphs.

    A paragraph break happens when the silence gap between two segments exceeds
    ``max_gap_s`` (and the current paragraph is long enough), or when the current
    paragraph exceeds ``target_chars`` at a sentence boundary.
    """
    paragraphs: list[Paragraph] = []
    current: list[str] = []
    current_start: float | None = None
    prev_end: float | None = None
    length = 0

    def flush() -> None:
        nonlocal current, length, current_start
        if current and current_start is not None:
            paragraphs.append(Paragraph(" ".join(current), current_start))
        current = []
        length = 0
        current_start = None

    for seg in segments:
        if (
            current
            and prev_end is not None
            and (seg.start - prev_end) > max_gap_s
            and length >= min_chars
        ):
            flush()
        if not current:
            current_start = seg.start
        current.append(seg.text)
        length += len(seg.text) + 1
        prev_end = seg.end
        if length >= target_chars and seg.text.rstrip().endswith(tuple(_SENTENCE_END)):
            flush()
    flush()
    return paragraphs


def format_timestamp(seconds: float) -> str:
    """Format seconds as mm:ss (or h:mm:ss beyond an hour)."""
    seconds = max(0, int(round(seconds)))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def render_transcript(
    paragraphs: list[Paragraph],
    *,
    with_timestamps: bool = True,
    interval_s: int = 45,
) -> str:
    """Render paragraphs as text, inserting a [mm:ss] marker roughly every
    ``interval_s`` seconds of audio (measured between paragraph start times)."""
    parts: list[str] = []
    last_marker: float | None = None
    for para in paragraphs:
        if with_timestamps and (last_marker is None or para.start - last_marker >= interval_s):
            parts.append(f"[{format_timestamp(para.start)}] {para.text}")
            last_marker = para.start
        else:
            parts.append(para.text)
    return "\n\n".join(parts)


def word_count(text: str) -> int:
    return len(text.split())


def parse_srt(content: str) -> list[Segment]:
    """Parse SRT subtitle content into segments (fallback when JSON is missing)."""
    _SRT_TIME_RE = re.compile(
        r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)"
    )
    segments: list[Segment] = []
    for block in re.split(r"\n\s*\n", content.strip()):
        lines = [line for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        time_line = next((line for line in lines if "-->" in line), None)
        if time_line is None:
            continue
        match = _SRT_TIME_RE.search(time_line)
        if match is None:
            continue
        text = " ".join(
            line.strip()
            for line in lines
            if line is not time_line and "-->" not in line and not line.strip().isdigit()
        )
        if not text:
            continue
        start = (
            int(match.group(1)) * 3600
            + int(match.group(2)) * 60
            + int(match.group(3))
            + int(match.group(4)) / 1000
        )
        end = (
            int(match.group(5)) * 3600
            + int(match.group(6)) * 60
            + int(match.group(7))
            + int(match.group(8)) / 1000
        )
        segments.append(Segment(start, end, text))
    return segments
