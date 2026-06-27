"""Financial grounding gate — the floor (rag-design.md §5).

Grounding strength is computed from the **financial branch only**, because that
branch carries the factual burden: a strong template/exemplar cannot rescue weak
evidence. Strength blends the top evidence score with the margin to the next
candidate (a single strong-but-isolated hit is less grounded than a strong hit
backed by corroborating evidence).

The decision is a three-way: ``PROCEED`` above the floor; ``RETRY`` to re-enter
the grounding loop on the financial branch (relax the hard match, broaden *k*)
while loops remain; ``REFUSE`` once they are exhausted — preserving the platform
rule of refusing rather than answering outside the corpus.
"""

from __future__ import annotations

from enum import StrEnum

from app.core.policies.retrieval import GroundingPolicy
from app.domain.ports.vector_store import ScoredChunk


class GroundingDecision(StrEnum):
    PROCEED = "proceed"
    RETRY = "retry"
    REFUSE = "refuse"


class GroundingEvaluator:
    """Computes financial grounding strength and the loop/refuse decision."""

    def __init__(self, policy: GroundingPolicy) -> None:
        self._policy = policy

    def strength(self, ranked_financial: list[ScoredChunk]) -> float:
        """Top evidence score lifted by corroboration (the top-2 margin).

        Empty (no period/entity-matched evidence) → 0.0, which always refuses.
        """
        if not ranked_financial:
            return 0.0
        top = max(0.0, ranked_financial[0].score)
        if len(ranked_financial) == 1:
            return top
        second = max(0.0, ranked_financial[1].score)
        # Corroboration bonus: up to +0.1 when a second hit is close behind.
        corroboration = 0.1 * (second / top) if top > 0 else 0.0
        return min(1.0, top + corroboration)

    def decide(self, strength: float, *, attempt: int) -> GroundingDecision:
        if strength >= self._policy.grounding_floor:
            return GroundingDecision.PROCEED
        if attempt < self._policy.max_grounding_loops:
            return GroundingDecision.RETRY
        return GroundingDecision.REFUSE

    @property
    def floor(self) -> float:
        return self._policy.grounding_floor

    @property
    def high_band(self) -> float:
        return self._policy.high_confidence_band
