"""In-memory human-review queue — Phase 1 implementation of ``HumanReviewQueuePort``.

Documents that fail the financial gate or fall below the classifier threshold are
parked here for an analyst instead of being indexed. Phase 1 keeps the queue in
process (no extra infrastructure); a durable table-backed queue can replace it
behind the same port when the review UI lands.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.domain.ingestion.lineage import HumanReviewItem


class InMemoryHumanReviewQueue:
    def __init__(self) -> None:
        self._items: list[HumanReviewItem] = []

    async def enqueue(self, item: HumanReviewItem) -> None:
        self._items.append(item)

    async def list_pending(self, *, limit: int = 50) -> Sequence[HumanReviewItem]:
        return list(self._items[:limit])

    async def count(self) -> int:
        return len(self._items)
