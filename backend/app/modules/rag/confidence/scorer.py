"""Confidence scoring — per-repository signals, gated by financial grounding
(rag-design.md §5).

Confidence is a composite of three signals, but the financial grounding signal is
**dominant and gating**: below the floor the band is forced to ``LOW`` regardless
of how strong the template and exemplar signals are ("a beautiful template and
great exemplars cannot rescue weak factual grounding"). Above the floor the
composite bands into ``HIGH`` (generate, cited) or ``MEDIUM`` (generate, flag
low-confidence sections).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.policies.retrieval import GroundingPolicy
from app.domain.proposals.enums import ConfidenceBand

# Composite weights — grounding dominates; template coverage and exemplar
# relevance contribute to framing confidence only.
_W_GROUNDING = 0.70
_W_TEMPLATE = 0.20
_W_EXEMPLAR = 0.10


@dataclass(frozen=True, slots=True)
class ConfidenceAssessment:
    score: float
    band: ConfidenceBand
    grounding_strength: float
    template_coverage: float
    exemplar_relevance: float


class ConfidenceScorer:
    def __init__(self, policy: GroundingPolicy) -> None:
        self._policy = policy

    def score(
        self,
        *,
        grounding_strength: float,
        template_coverage: float,
        exemplar_relevance: float,
    ) -> ConfidenceAssessment:
        composite = (
            _W_GROUNDING * grounding_strength
            + _W_TEMPLATE * _clamp(template_coverage)
            + _W_EXEMPLAR * _clamp(exemplar_relevance)
        )
        band = self._band(grounding_strength, composite)
        return ConfidenceAssessment(
            score=round(composite, 4),
            band=band,
            grounding_strength=grounding_strength,
            template_coverage=_clamp(template_coverage),
            exemplar_relevance=_clamp(exemplar_relevance),
        )

    def _band(self, grounding_strength: float, composite: float) -> ConfidenceBand:
        if grounding_strength < self._policy.grounding_floor:
            return ConfidenceBand.LOW  # gate: weak grounding cannot be rescued
        if composite >= self._policy.high_confidence_band:
            return ConfidenceBand.HIGH
        return ConfidenceBand.MEDIUM


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
