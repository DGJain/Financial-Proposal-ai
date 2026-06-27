"""Document-catalog port — PostgreSQL is the system of record for documents.

Keyed by ``repository`` and ``subtype`` (architecture.md §6) so lineage and
metrics can be sliced per repository. ``exists_by_content_hash`` backs
re-ingestion idempotency / dedup (avoids duplicate exemplars skewing Corpus
Contribution).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol, runtime_checkable

from app.domain.documents.document import Document
from app.domain.repositories.repository import Repository


@runtime_checkable
class DocumentCatalogPort(Protocol):
    async def add(self, document: Document) -> None:
        ...

    async def get(self, doc_id: str) -> Document | None:
        ...

    async def exists_by_content_hash(self, content_hash: str) -> bool:
        """Idempotency check for uploads and approved-proposal re-ingestion."""
        ...

    async def list_by_repository(
        self,
        repository: Repository,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Document]:
        ...

    async def count_by_repository(self, repository: Repository) -> int:
        """Backs the dashboard repository cards (doc counts per repository)."""
        ...

    async def latest_ingestion_ts(self, repository: Repository) -> datetime | None:
        """Most recent successful ingestion timestamp in a repository.

        Backs the dashboard's "Last Ingestion" repo card (corpus freshness);
        ``None`` when the repository holds no documents yet (ui-design.md §6.7).
        """
        ...
