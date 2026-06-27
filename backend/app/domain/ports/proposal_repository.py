"""Proposal-repository port — PostgreSQL persistence for the proposal aggregate.

The ``GenerationEvent`` lineage already persists *what happened*; this port
persists the produced **document**: the ``Proposal`` aggregate root and its
immutable ``ProposalVersion`` snapshots (ui-design.md Page 3 editing contract).
Structure is locked — the adapter stores sections in order so the side-by-side
editor can validate that an edit changed only prose, never the template skeleton.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from app.domain.proposals.enums import ProposalStatus
from app.domain.proposals.proposal import Proposal, ProposalVersion


@runtime_checkable
class ProposalRepositoryPort(Protocol):
    async def add(self, proposal: Proposal) -> None:
        """Persist a new proposal aggregate (its draft version and sections)."""
        ...

    async def get(self, proposal_id: str) -> Proposal | None:
        """Reconstruct a proposal with all its versions (newest derivable)."""
        ...

    async def add_version(self, proposal_id: str, version: ProposalVersion) -> None:
        """Append a new immutable version (a text-only edit) to an existing
        proposal and advance its status to the version's status. Versions are
        append-only — prior snapshots are never mutated."""
        ...

    async def set_status(self, proposal_id: str, status: ProposalStatus) -> None:
        """Advance the aggregate's lifecycle status without adding a version.

        Used by export to mark a proposal ``EXPORTED`` (the rendered prose is
        unchanged — only the lifecycle moves). Raises if the proposal is unknown.
        """
        ...

    async def list_recent(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Proposal]:
        """Proposal history rows (newest first)."""
        ...
