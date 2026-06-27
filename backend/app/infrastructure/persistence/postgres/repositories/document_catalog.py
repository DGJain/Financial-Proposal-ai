"""SQLAlchemy adapter implementing ``DocumentCatalogPort``."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.documents.document import Document
from app.domain.repositories.repository import Repository
from app.infrastructure.persistence.postgres.mappers import document_mapper
from app.infrastructure.persistence.postgres.models.document import DocumentRow


class SqlAlchemyDocumentCatalog:
    """Catalog read/write over one ``AsyncSession`` (owned by the Unit of Work)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, document: Document) -> None:
        self._session.add(document_mapper.to_row(document))

    async def get(self, doc_id: str) -> Document | None:
        row = await self._session.get(DocumentRow, doc_id)
        return document_mapper.to_domain(row) if row is not None else None

    async def exists_by_content_hash(self, content_hash: str) -> bool:
        stmt = select(DocumentRow.doc_id).where(DocumentRow.content_hash == content_hash)
        result = await self._session.execute(stmt.limit(1))
        return result.first() is not None

    async def list_by_repository(
        self,
        repository: Repository,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Document]:
        stmt = (
            select(DocumentRow)
            .where(DocumentRow.repository == repository.value)
            .order_by(DocumentRow.ingestion_ts.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [document_mapper.to_domain(row) for row in rows]

    async def count_by_repository(self, repository: Repository) -> int:
        stmt = select(func.count()).select_from(DocumentRow).where(
            DocumentRow.repository == repository.value
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def latest_ingestion_ts(self, repository: Repository) -> datetime | None:
        stmt = select(func.max(DocumentRow.ingestion_ts)).where(
            DocumentRow.repository == repository.value
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()
