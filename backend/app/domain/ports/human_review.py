"""Human-review queue port — where documents go when they can't be auto-indexed.

A document that fails the financial quality gate or whose repository classifier is
below threshold must **never** enter the index (architecture.md: the financial
repo is the only citable evidence, so an unverified figure cannot be retrievable).
Instead it is enqueued here for an analyst. The concrete queue (in-memory for
Phase 1; a durable table later) sits behind this Protocol.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from app.domain.ingestion.lineage import HumanReviewItem


@runtime_checkable
class HumanReviewQueuePort(Protocol):
    async def enqueue(self, item: HumanReviewItem) -> None:
        ...

    async def list_pending(self, *, limit: int = 50) -> Sequence[HumanReviewItem]:
        ...

    async def count(self) -> int:
        ...
