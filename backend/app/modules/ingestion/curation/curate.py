"""Curation entry point — the approval gate for the curated repositories.

``repo_proposals`` and ``repo_templates`` are manually curated, never open-upload
(architecture §6). This use-case is the *only* way content reaches them: it routes
to the declared target repository and lets the engine run the anonymization
verification (for proposals) and the repository gate before anything is indexed.
Financial content does not come through here — it uses the open-upload entry.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.domain.repositories.repository import Repository

if TYPE_CHECKING:
    from app.domain.ingestion.lineage import IngestionResult
    from app.modules.ingestion.pipeline.engine import IngestionEngine, IngestionRequest

_CURATED_REPOSITORIES = frozenset({Repository.PROPOSAL, Repository.TEMPLATE})


class CurateExemplar:
    """Use-case: curate a proposal/template into its approval-gated repository."""

    def __init__(self, engine: IngestionEngine) -> None:
        self._engine = engine

    async def execute(
        self, request: IngestionRequest, *, target: Repository
    ) -> IngestionResult:
        if target not in _CURATED_REPOSITORIES:
            raise ValueError(
                "Curation targets the proposal or template repository only; "
                "financial content uses the open-upload entry."
            )
        return await self._engine.execute(request, target_override=target)
