"""Audit-log port — append-only, replayable generation lineage.

Backs the Execution Report and the contribution metrics (ui-design.md §6.6).
Append-only by contract: there is no update or delete — corrections are new
events. Refused runs are recorded too, so every prompt has a replayable report.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol, runtime_checkable

from app.domain.generation.generation_event import GenerationEvent


@runtime_checkable
class AuditLogPort(Protocol):
    async def append(self, event: GenerationEvent) -> None:
        """Persist an immutable generation-lineage record."""
        ...

    async def get(self, gen_id: str) -> GenerationEvent | None:
        """Reconstruct one run for the Execution Report (`/report/[id]`)."""
        ...

    async def list_recent(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[GenerationEvent]:
        """Prompt-history rows (newest first)."""
        ...

    async def list_since(self, since: datetime) -> Sequence[GenerationEvent]:
        """Window for generation-health aggregates (e.g. 7-day chart)."""
        ...
