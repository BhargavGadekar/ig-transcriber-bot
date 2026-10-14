"""SQLite persistence via aiosqlite: job tracking, transcript cache, user settings."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    chat_id     INTEGER NOT NULL,
    message_id  INTEGER,
    url         TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'queued',
    error       TEXT,
    md_filename TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_user_created ON jobs(user_id, created_at);

CREATE TABLE IF NOT EXISTS transcripts (
    url_key       TEXT PRIMARY KEY,
    meta_json     TEXT NOT NULL,
    segments_json TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_settings (
    user_id     INTEGER PRIMARY KEY,
    timestamps  INTEGER NOT NULL DEFAULT 1,
    script_mode TEXT NOT NULL DEFAULT 'roman',
    updated_at  TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    """Thin async wrapper around a single aiosqlite connection."""

    def __init__(self, path: Path):
        self._path = Path(path)
        self._conn: aiosqlite.Connection | None = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database.connect() has not been called")
        return self._conn

    async def connect(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(_SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    # --- jobs ---------------------------------------------------------------

    async def add_job(
        self, user_id: int, chat_id: int, message_id: int | None, url: str
    ) -> int:
        now = _now()
        cur = await self.conn.execute(
            "INSERT INTO jobs (user_id, chat_id, message_id, url, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 'queued', ?, ?)",
            (user_id, chat_id, message_id, url, now, now),
        )
        await self.conn.commit()
        return int(cur.lastrowid or 0)

    async def update_job(
        self,
        job_id: int,
        *,
        status: str,
        error: str | None = None,
        md_filename: str | None = None,
    ) -> None:
        await self.conn.execute(
            "UPDATE jobs SET status = ?, error = ?, md_filename = COALESCE(?, md_filename), "
            "updated_at = ? WHERE id = ?",
            (status, error, md_filename, _now(), job_id),
        )
        await self.conn.commit()

    async def cleanup_stale_jobs(self) -> int:
        """Mark any unfinished jobs from an interrupted process as failed."""
        cur = await self.conn.execute(
            "UPDATE jobs SET status = 'failed', error = 'Interrupted by bot restart', updated_at = ? "
            "WHERE status IN ('queued', 'downloading', 'waiting', 'extracting', 'transcribing', 'summarizing')",
            (_now(),),
        )
        await self.conn.commit()
        return cur.rowcount

    async def last_job_for_user(self, user_id: int) -> dict[str, Any] | None:
        async with self.conn.execute(
            "SELECT * FROM jobs WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def count_recent_jobs(self, user_id: int, *, hours: int = 1) -> int:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(hours=hours)
        ).isoformat(timespec="seconds")
        async with self.conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE user_id = ? AND created_at >= ?",
            (user_id, cutoff),
        ) as cur:
            row = await cur.fetchone()
        return int(row[0]) if row else 0

    # --- transcript cache ----------------------------------------------------

    async def get_transcript(self, url_key: str) -> tuple[dict, list[dict]] | None:
        async with self.conn.execute(
            "SELECT meta_json, segments_json FROM transcripts WHERE url_key = ?",
            (url_key,),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        return json.loads(row[0]), json.loads(row[1])

    async def put_transcript(self, url_key: str, meta: dict, segments: list[dict]) -> None:
        await self.conn.execute(
            "INSERT OR REPLACE INTO transcripts (url_key, meta_json, segments_json, created_at) "
            "VALUES (?, ?, ?, ?)",
            (url_key, json.dumps(meta, ensure_ascii=False), json.dumps(segments, ensure_ascii=False), _now()),
        )
        await self.conn.commit()

    # --- user settings ----------------------------------------------------------

    async def get_user_settings(self, user_id: int) -> dict[str, Any] | None:
        async with self.conn.execute(
            "SELECT timestamps, script_mode FROM user_settings WHERE user_id = ?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        return {"timestamps": bool(row[0]), "script_mode": row[1]}

    async def set_user_settings(
        self, user_id: int, *, timestamps: bool, script_mode: str
    ) -> None:
        await self.conn.execute(
            "INSERT INTO user_settings (user_id, timestamps, script_mode, updated_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET timestamps = excluded.timestamps, "
            "script_mode = excluded.script_mode, updated_at = excluded.updated_at",
            (user_id, int(timestamps), script_mode, _now()),
        )
        await self.conn.commit()
