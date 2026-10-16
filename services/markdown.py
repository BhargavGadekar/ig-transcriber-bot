"""Obsidian-flavoured Markdown rendering of transcripts."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone

from utils.files import sanitize_filename_part, short_id
from utils.text import format_timestamp
from utils.urls import is_youtube_url


@dataclass(slots=True)
class VideoMeta:
    """Metadata about a transcribed video, gathered at download time."""

    url: str
    author: str = ""
    title: str = ""
    upload_date: date | None = None
    duration_s: int | None = None
    caption: str | None = None
    language: str = ""
    model_name: str = ""
    summary: str | None = None
    transcript_text: str | None = None

    def to_dict(self) -> dict:
        data = asdict(self)
        data["upload_date"] = self.upload_date.isoformat() if self.upload_date else None
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "VideoMeta":
        upload = data.get("upload_date")
        if isinstance(upload, date):
            upload_date = upload
        elif upload:
            try:
                upload_date = date.fromisoformat(str(upload))
            except ValueError:
                upload_date = None
        else:
            upload_date = None
        return cls(
            url=data.get("url", ""),
            author=data.get("author", ""),
            title=data.get("title", ""),
            upload_date=upload_date,
            duration_s=data.get("duration_s"),
            caption=data.get("caption"),
            language=data.get("language", ""),
            model_name=data.get("model_name", ""),
            summary=data.get("summary"),
            transcript_text=data.get("transcript_text"),
        )


def _yaml(value) -> str:
    """Render a scalar as a YAML double-quoted string (json.dumps output is
    valid YAML); safely escapes colons, quotes and newlines that Instagram
    titles/captions are full of."""
    if value is None:
        return '""'
    return json.dumps(str(value), ensure_ascii=False)


def render_markdown(
    meta: VideoMeta,
    transcript_text: str,
    *,
    summary_markdown: str | None = None,
    transcribed_at: datetime | None = None,
) -> str:
    """Render the Obsidian-ready note: YAML frontmatter + body per template."""
    is_yt = is_youtube_url(meta.url)
    default_title = "YouTube Short" if is_yt else "Instagram video"
    platform_name = "youtube" if is_yt else "instagram"
    tag_platform = "youtube" if is_yt else "instagram"

    title = (meta.title or "").strip() or default_title
    duration = format_timestamp(meta.duration_s) if meta.duration_s else ""
    uploaded = meta.upload_date.isoformat() if meta.upload_date else ""
    transcribed = (transcribed_at or datetime.now(timezone.utc)).isoformat(timespec="seconds")

    summary_content = summary_markdown or meta.summary
    tag_list = ["transcript", tag_platform]
    if summary_content:
        tag_list.append("summary")

    lines = [
        "---",
        f"source: {_yaml(meta.url)}",
        f"platform: {platform_name}",
        f"author: {_yaml(meta.author)}",
        f"title: {_yaml(title)}",
        f"uploaded: {_yaml(uploaded)}",
        f"duration: {_yaml(duration)}",
        f"language: {_yaml(meta.language)}",
        f"transcribed: {_yaml(transcribed)}",
        f"model: {_yaml(meta.model_name)}",
        f"tags: [{', '.join(tag_list)}]",
        "---",
        "",
        f"# {title}",
        "",
        f"**Video:** [{meta.url}]({meta.url})",
    ]

    if summary_content and summary_content.strip():
        lines += [
            "",
            "## 📌 AI Summary & Analysis",
            "",
            summary_content.strip(),
            "",
            "---",
        ]

    lines += [
        "",
        "## Transcript",
        "",
        transcript_text.strip() or "_(no speech detected)_",
    ]
    if meta.caption and meta.caption.strip():
        lines += ["", "## Caption", "", meta.caption.strip()]
    lines.append("")
    return "\n".join(lines)


def build_md_filename(meta: VideoMeta, *, date_override: date | None = None) -> str:
    """Filename: YYYY-MM-DD_<sanitized-author-or-title>_<shortid>.md.

    The date is the video's upload date when known (keeps an Obsidian vault in
    chronological order), otherwise today's date.
    """
    day = date_override or meta.upload_date or date.today()
    fallback_part = "youtube" if is_youtube_url(meta.url) else "instagram"
    part = sanitize_filename_part(meta.author or meta.title or fallback_part, max_len=40)
    return f"{day:%Y-%m-%d}_{part}_{short_id(meta.url)}.md"
