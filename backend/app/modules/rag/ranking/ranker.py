"""Within-repository ranking (rag-design.md §4) — never a global pool.

Each repository's candidates are ranked against a *repository-specific* criterion,
then handed on **separately** so the assembler can allocate a context budget by
weight. Cross-repository score comparison is explicitly rejected: a highly similar
past proposal must never outrank the financial evidence the proposal is built on.

Per-repository criteria:

* **financial** — a **hard** period/entity match (wrong-period or wrong-entity
  evidence is *dropped*, not down-weighted) and then descending similarity. The
  hard match is relaxable by the grounding loop via :class:`Relaxation`.
* **proposal** — descending similarity with an ``outcome == won`` boost, so
  successful precedents inform framing first.
* **template** — the single best-matching approved scaffold (top-1), preferring a
  ``subtype`` that matches the brief's ``proposal_type``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.generation.brief import GenerationBrief
from app.domain.ports.vector_store import ScoredChunk
from app.domain.proposals.enums import Outcome
from app.domain.repositories.repository import Repository
from app.modules.rag.retrievers.federated import CandidatePool

# How much an ``outcome == won`` exemplar is boosted in proposal ranking.
WON_OUTCOME_BOOST = 0.15


@dataclass(frozen=True, slots=True)
class Relaxation:
    """Grounding-loop relaxation of the financial hard-match constraints.

    Loop 0 enforces both period and entity; each subsequent loop relaxes one
    constraint so weak grounding can broaden its evidence before refusing.
    """

    require_period: bool = True
    require_entity: bool = True

    @staticmethod
    def for_attempt(attempt: int) -> Relaxation:
        if attempt <= 0:
            return Relaxation(require_period=True, require_entity=True)
        if attempt == 1:
            return Relaxation(require_period=True, require_entity=False)
        return Relaxation(require_period=False, require_entity=False)


@dataclass(frozen=True, slots=True)
class RankedCandidates:
    """Within-repo ordered candidate lists (no cross-repo comparison)."""

    by_repository: dict[Repository, list[ScoredChunk]] = field(default_factory=dict)

    def get(self, repository: Repository) -> list[ScoredChunk]:
        return self.by_repository.get(repository, [])


class WithinRepoRanker:
    """Ranks each repository's candidates by its own criterion."""

    def rank(
        self,
        pool: CandidatePool,
        brief: GenerationBrief,
        *,
        relaxation: Relaxation = Relaxation(),
    ) -> RankedCandidates:
        return RankedCandidates(
            by_repository={
                Repository.FINANCIAL: self._rank_financial(
                    pool.get(Repository.FINANCIAL), brief, relaxation
                ),
                Repository.PROPOSAL: self._rank_proposal(pool.get(Repository.PROPOSAL)),
                Repository.TEMPLATE: self._rank_template(
                    pool.get(Repository.TEMPLATE), brief
                ),
            }
        )

    def _rank_financial(
        self,
        candidates: list[ScoredChunk],
        brief: GenerationBrief,
        relaxation: Relaxation,
    ) -> list[ScoredChunk]:
        kept = [c for c in candidates if self._period_entity_ok(c, brief, relaxation)]
        return sorted(kept, key=lambda c: c.score, reverse=True)

    def _period_entity_ok(
        self, candidate: ScoredChunk, brief: GenerationBrief, relaxation: Relaxation
    ) -> bool:
        md = candidate.chunk.metadata
        if relaxation.require_period and brief.fiscal_year is not None:
            fy = md.get("fiscal_year")
            if fy is not None and int(fy) != brief.fiscal_year:
                return False  # wrong-period evidence is dropped, not down-weighted
        if relaxation.require_entity and brief.entity:
            issuer = str(md.get("issuer", ""))
            if issuer and brief.entity.lower() not in issuer.lower():
                return False
        return True

    def _rank_proposal(self, candidates: list[ScoredChunk]) -> list[ScoredChunk]:
        def keyed(c: ScoredChunk) -> float:
            boost = WON_OUTCOME_BOOST if c.chunk.metadata.get("outcome") == Outcome.WON.value else 0.0
            return c.score + boost

        return sorted(candidates, key=keyed, reverse=True)

    def _rank_template(
        self, candidates: list[ScoredChunk], brief: GenerationBrief
    ) -> list[ScoredChunk]:
        # Deterministic scaffold selection: prefer a subtype matching the brief's
        # proposal_type, then highest similarity. All approved candidates are kept
        # in order (the assembler takes the scaffold slot first), best-first.
        def keyed(c: ScoredChunk) -> tuple[int, float]:
            subtype = str(c.chunk.metadata.get("subtype", ""))
            type_match = 1 if subtype and subtype in brief.proposal_type else 0
            return (type_match, c.score)

        return sorted(candidates, key=keyed, reverse=True)
