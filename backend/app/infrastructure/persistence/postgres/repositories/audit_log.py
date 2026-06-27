"""SQLAlchemy adapter implementing ``AuditLogPort`` — append-only by contract.

There is deliberately no update or delete: the immutable lineage is the platform's
audit guarantee. Reads eager-load the four child collections so the Execution
Report reconstructs without lazy-load round-trips (and without async lazy-load
errors).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.generation.generation_event import GenerationEvent
from app.infrastructure.persistence.postgres.mappers import generation_mapper
from app.infrastructure.persistence.postgres.models.generation import GenerationEventRow

_CHILD_LOADS = (
    selectinload(GenerationEventRow.retrieval_hits),
    selectinload(GenerationEventRow.citations),
    selectinload(GenerationEventRow.stage_timings),
    selectinload(GenerationEventRow.gate_outcomes),
)


class SqlAlchemyAuditLog:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, event: GenerationEvent) -> None:
        self._session.add(generation_mapper.to_row(event))

    async def get(self, gen_id: str) -> GenerationEvent | None:
        stmt = (
            select(GenerationEventRow)
            .where(GenerationEventRow.gen_id == gen_id)
            .options(*_CHILD_LOADS)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return generation_mapper.to_domain(row) if row is not None else None

    async def list_recent(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[GenerationEvent]:
        stmt = (
            select(GenerationEventRow)
            .order_by(GenerationEventRow.ts.desc())
            .limit(limit)
            .offset(offset)
            .options(*_CHILD_LOADS)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [generation_mapper.to_domain(row) for row in rows]

    async def list_since(self, since: datetime) -> Sequence[GenerationEvent]:
        stmt = (
            select(GenerationEventRow)
            .where(GenerationEventRow.ts >= since)
            .order_by(GenerationEventRow.ts.asc())
            .options(*_CHILD_LOADS)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [generation_mapper.to_domain(row) for row in rows]
