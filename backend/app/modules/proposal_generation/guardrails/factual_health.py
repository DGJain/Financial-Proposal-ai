"""Factual-contribution health guardrail (rag-design.md §6b).

This is a **guardrail, not a dashboard tile**: it reads the computed factual
contribution and blocks when the financial repository's factual share falls below
its floor — the signature of cross-engagement figure leakage. A clean run has
~100% financial factual share; any non-financial factual contribution trips it.

Returns a :class:`GateOutcome` so the decision is recorded in the generation
lineage regardless of verdict (block & regenerate, or pass).
"""

from __future__ import annotations

from app.core.policies.retrieval import GroundingPolicy
from app.domain.generation.enums import GenerationGateVerdict
from app.domain.generation.generation_event import GateOutcome
from app.domain.metrics.contribution import ContributionBreakdown

GATE_NAME = "factual_health"


class FactualHealthGuard:
    def __init__(self, policy: GroundingPolicy) -> None:
        # Policy floor is a fraction (0.999); contribution shares are percentages.
        self._floor_pct = policy.min_financial_factual_share * 100.0

    def check(self, contribution: ContributionBreakdown) -> GateOutcome:
        ok = contribution.factual_health_ok(
            min_financial_factual_share_pct=self._floor_pct
        )
        financial = contribution.factual_share.financial
        verdict = GenerationGateVerdict.PASS if ok else GenerationGateVerdict.BLOCK_REGENERATE
        detail = (
            f"financial factual share {financial:.3f}% "
            f"(floor {self._floor_pct:.3f}%)"
        )
        return GateOutcome(name=GATE_NAME, verdict=verdict, detail=detail)
