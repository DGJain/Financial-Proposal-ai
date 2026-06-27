"""Federated, role-aware retrieval fan-out (rag-design.md §1).

Three branch retrievers run **concurrently** (``asyncio.gather``) over the single
``VectorStorePort.query`` seam — each targets one collection with its own query
text, candidate budget *k*, and metadata ``where`` filter. ACL is enforced inside
the port (engagement pre-filter + fail-closed group/classification post-filter),
so a caller in the wrong engagement retrieves nothing from any branch.

The branches are **never pooled into one ranking**: the result is a role-tagged
:class:`CandidatePool` keyed by repository, which the within-repo ranker consumes
next. The financial branch's *k* can be broadened by the grounding loop; the other
branches keep their fixed budgets.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from app.core.policies.retrieval import BranchBudget
from app.domain.ports.embedder import EmbedderPort
from app.domain.ports.vector_store import AclFilter, ScoredChunk, VectorStorePort
from app.domain.repositories.repository import Repository
from app.modules.rag.query.formulator import BranchQueries, BranchQuery


@dataclass(frozen=True, slots=True)
class CandidatePool:
    """Role-tagged retrieval candidates — one ordered list per repository.

    Kept strictly separate by repository so style/structure can never outrank
    evidence by raw score (rag-design.md §4 rejects global pooling).
    """

    by_repository: dict[Repository, list[ScoredChunk]] = field(default_factory=dict)

    def get(self, repository: Repository) -> list[ScoredChunk]:
        return self.by_repository.get(repository, [])

    @property
    def total(self) -> int:
        return sum(len(v) for v in self.by_repository.values())


class FederatedRetriever:
    """Fans out the three branch queries concurrently and tags results by role."""

    def __init__(
        self,
        *,
        vector_store: VectorStorePort,
        embedder: EmbedderPort,
        budget: BranchBudget,
    ) -> None:
        self._vector_store = vector_store
        self._embedder = embedder
        self._budget = budget

    async def retrieve(
        self,
        queries: BranchQueries,
        acl: AclFilter,
        *,
        financial_k: int | None = None,
    ) -> CandidatePool:
        """Run all three branches concurrently; ``financial_k`` overrides the
        evidence budget when the grounding loop broadens recall."""
        ks = {
            Repository.FINANCIAL: financial_k or self._budget.financial_k,
            Repository.PROPOSAL: self._budget.proposal_k,
            Repository.TEMPLATE: self._budget.template_k,
        }
        results = await asyncio.gather(
            *(self._branch(q, acl, ks[q.repository]) for q in queries.all())
        )
        return CandidatePool(by_repository={repo: hits for repo, hits in results})

    async def _branch(
        self, query: BranchQuery, acl: AclFilter, k: int
    ) -> tuple[Repository, list[ScoredChunk]]:
        embedding = await self._embedder.embed_query(query.text)
        hits = await self._vector_store.query(
            query.repository,
            embedding,
            k=k,
            acl=acl,
            where=query.where or None,
        )
        return query.repository, hits
