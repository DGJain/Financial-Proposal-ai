"""SQLAlchemy Unit of Work — the transactional boundary for use-cases.

Implements ``UnitOfWorkPort``: opens one ``AsyncSession``, exposes the catalog
and audit adapters bound to it, and commits/rolls back atomically. Exiting the
context without an explicit ``commit`` rolls back (fail-safe), so a use-case that
raises midway never leaves a partial write.
"""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.ports.audit_log import AuditLogPort
from app.domain.ports.chunk_catalog import ChunkCatalogPort
from app.domain.ports.document_catalog import DocumentCatalogPort
from app.domain.ports.ingestion_lineage import IngestionLineagePort
from app.domain.ports.proposal_repository import ProposalRepositoryPort
from app.infrastructure.persistence.postgres.engine import get_session_factory
from app.infrastructure.persistence.postgres.repositories.audit_log import SqlAlchemyAuditLog
from app.infrastructure.persistence.postgres.repositories.chunk_catalog import (
    SqlAlchemyChunkCatalog,
)
from app.infrastructure.persistence.postgres.repositories.document_catalog import (
    SqlAlchemyDocumentCatalog,
)
from app.infrastructure.persistence.postgres.repositories.ingestion_lineage import (
    SqlAlchemyIngestionLineage,
)
from app.infrastructure.persistence.postgres.repositories.proposal_repository import (
    SqlAlchemyProposalRepository,
)


class SqlAlchemyUnitOfWork:
    # Typed as the domain ports so the UoW is assignable to ``UnitOfWorkPort``
    # (Protocol attributes are invariant); the concrete adapters satisfy them.
    documents: DocumentCatalogPort
    chunks: ChunkCatalogPort
    lineage: IngestionLineagePort
    audit: AuditLogPort
    proposals: ProposalRepositoryPort

    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        self._session_factory = session_factory or get_session_factory()

    async def __aenter__(self) -> SqlAlchemyUnitOfWork:
        self._session = self._session_factory()
        self.documents = SqlAlchemyDocumentCatalog(self._session)
        self.chunks = SqlAlchemyChunkCatalog(self._session)
        self.lineage = SqlAlchemyIngestionLineage(self._session)
        self.audit = SqlAlchemyAuditLog(self._session)
        self.proposals = SqlAlchemyProposalRepository(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            await self.rollback()  # no-op if already committed; safety net otherwise
        finally:
            await self._session.close()

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
