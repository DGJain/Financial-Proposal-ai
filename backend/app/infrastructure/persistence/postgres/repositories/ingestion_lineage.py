"""SQLAlchemy adapter implementing ``IngestionLineagePort``."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.ingestion.lineage import IngestionLineage
from app.infrastructure.persistence.postgres.mappers import quality_mapper
from app.infrastructure.persistence.postgres.models.document import DocumentQualityRow


class SqlAlchemyIngestionLineage:
    """Ingestion-lineage read/write over one ``AsyncSession`` (owned by the UoW)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, lineage: IngestionLineage) -> None:
        self._session.add(quality_mapper.to_row(lineage))

    async def get(self, doc_id: str) -> IngestionLineage | None:
        row = await self._session.get(DocumentQualityRow, doc_id)
        return quality_mapper.to_domain(row) if row is not None else None

    async def get_many(
        self, doc_ids: Sequence[str]
    ) -> Mapping[str, IngestionLineage]:
        unique = list(dict.fromkeys(doc_ids))  # de-dup, preserve order
        if not unique:
            return {}
        stmt = select(DocumentQualityRow).where(DocumentQualityRow.doc_id.in_(unique))
        rows = (await self._session.execute(stmt)).scalars().all()
        return {row.doc_id: quality_mapper.to_domain(row) for row in rows}
