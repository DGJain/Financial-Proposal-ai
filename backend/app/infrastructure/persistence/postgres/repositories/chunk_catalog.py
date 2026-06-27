"""SQLAlchemy adapter implementing ``ChunkCatalogPort``."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.chunks.chunk import Chunk
from app.domain.repositories.repository import Repository
from app.infrastructure.persistence.postgres.mappers import chunk_mapper
from app.infrastructure.persistence.postgres.models.document import DocumentChunkRow


class SqlAlchemyChunkCatalog:
    """Chunk catalog read/write over one ``AsyncSession`` (owned by the Unit of Work)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_many(self, chunks: Sequence[Chunk]) -> None:
        self._session.add_all([chunk_mapper.to_row(chunk) for chunk in chunks])

    async def get(self, chunk_id: str) -> Chunk | None:
        row = await self._session.get(DocumentChunkRow, chunk_id)
        return chunk_mapper.to_domain(row) if row is not None else None

    async def list_by_document(self, doc_id: str) -> Sequence[Chunk]:
        stmt = (
            select(DocumentChunkRow)
            .where(DocumentChunkRow.doc_id == doc_id)
            .order_by(DocumentChunkRow.ordinal)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [chunk_mapper.to_domain(row) for row in rows]

    async def count_by_repository(self, repository: Repository) -> int:
        stmt = select(func.count()).select_from(DocumentChunkRow).where(
            DocumentChunkRow.repository == repository.value
        )
        return int((await self._session.execute(stmt)).scalar_one())
