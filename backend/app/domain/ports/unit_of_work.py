"""Unit-of-Work port — transactional boundary over the catalog/audit stores.

Use-cases acquire a UoW, perform catalog + audit writes, and commit atomically.
The concrete implementation (SQLAlchemy async session) lives in
``infrastructure.persistence``; use-cases see only this Protocol.
"""

from __future__ import annotations

from types import TracebackType
from typing import Protocol, runtime_checkable

from app.domain.ports.audit_log import AuditLogPort
from app.domain.ports.chunk_catalog import ChunkCatalogPort
from app.domain.ports.document_catalog import DocumentCatalogPort
from app.domain.ports.ingestion_lineage import IngestionLineagePort
from app.domain.ports.proposal_repository import ProposalRepositoryPort


@runtime_checkable
class UnitOfWorkPort(Protocol):
    """Async context manager exposing repositories within one transaction."""

    documents: DocumentCatalogPort
    chunks: ChunkCatalogPort
    lineage: IngestionLineagePort
    audit: AuditLogPort
    proposals: ProposalRepositoryPort

    async def __aenter__(self) -> UnitOfWorkPort:
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        ...

    async def commit(self) -> None:
        ...

    async def rollback(self) -> None:
        ...
