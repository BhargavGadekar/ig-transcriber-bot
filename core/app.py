"""Application context container passed to handlers."""
from __future__ import annotations

from dataclasses import dataclass

from core.database import Database
from core.pipeline import JobManager


@dataclass(slots=True)
class AppContext:
    settings: "object"  # core.config.Settings (typed loosely to avoid an import cycle)
    db: Database
    jobs: JobManager

    def stats(self) -> dict:
        return self.jobs.stats()
