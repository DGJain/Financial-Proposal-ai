"""Ingestion-lineage port — append-only record of each document's gate decision.

Persists the ``IngestionLineage`` audit record (π_d, classifier confidence,
quality scores, gate verdict, redaction-ledger reference) so every ingestion is
replayable against the policy snapshot that produced it. Written in the same Unit
of Work as the catalog ``Document`` row it describes.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable

from app.domain.ingestion.lineage import IngestionLineage


@runtime_checkable
class IngestionLineagePort(Protocol):
    async def add(self, lineage: IngestionLineage) -> None:
        ...

    async def get(self, doc_id: str) -> IngestionLineage | None:
        ...

    async def get_many(
        self, doc_ids: Sequence[str]
    ) -> Mapping[str, IngestionLineage]:
        """Batch-read quality lineage for many documents in one query.

        Backs the Execution Report and Prompt-History rows, which join each run's
        retrieved financial documents to their per-document quality (OCR / EQS /
        information-loss) — fetched in a single round-trip to avoid N+1 reads.
        Missing ``doc_id`` keys are simply absent from the result.
        """
        ...
