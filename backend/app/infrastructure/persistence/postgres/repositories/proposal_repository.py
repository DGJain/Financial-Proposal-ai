"""SQLAlchemy adapter implementing ``ProposalRepositoryPort``.

Reads eager-load versions → sections so the aggregate reconstructs without async
lazy-load round-trips (mirrors the audit-log adapter's child loading).
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.proposals.enums import ProposalStatus
from app.domain.proposals.proposal import Proposal, ProposalVersion
from app.infrastructure.persistence.postgres.mappers import proposal_mapper
from app.infrastructure.persistence.postgres.models.proposal import (
    ProposalRow,
    ProposalSectionRow,
    ProposalVersionRow,
)

_CHILD_LOADS = (
    selectinload(ProposalRow.versions).selectinload(ProposalVersionRow.sections),
)


class SqlAlchemyProposalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, proposal: Proposal) -> None:
        self._session.add(proposal_mapper.to_row(proposal))

    async def add_version(self, proposal_id: str, version: ProposalVersion) -> None:
        row = await self._session.get(ProposalRow, proposal_id)
        if row is None:
            raise KeyError(f"proposal {proposal_id!r} not found")
        self._session.add(
            ProposalVersionRow(
                proposal_id=proposal_id,
                version_no=version.version_no,
                created_ts=version.created_ts,
                created_by=version.created_by,
                status=version.status.value,
                sections=[
                    ProposalSectionRow(
                        section_id=s.section_id,
                        slot=s.slot,
                        heading=s.heading,
                        order=s.order,
                        body=s.body,
                    )
                    for s in version.sections
                ],
            )
        )
        # Advance the aggregate's lifecycle to mirror the newest version.
        row.status = version.status.value

    async def set_status(self, proposal_id: str, status: ProposalStatus) -> None:
        row = await self._session.get(ProposalRow, proposal_id)
        if row is None:
            raise KeyError(f"proposal {proposal_id!r} not found")
        row.status = status.value

    async def get(self, proposal_id: str) -> Proposal | None:
        stmt = (
            select(ProposalRow)
            .where(ProposalRow.proposal_id == proposal_id)
            .options(*_CHILD_LOADS)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return proposal_mapper.to_domain(row) if row is not None else None

    async def list_recent(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Proposal]:
        stmt = (
            select(ProposalRow)
            .order_by(ProposalRow.proposal_id.desc())
            .limit(limit)
            .offset(offset)
            .options(*_CHILD_LOADS)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [proposal_mapper.to_domain(row) for row in rows]
