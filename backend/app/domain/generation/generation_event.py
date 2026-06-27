"""GenerationEvent — the auditable record of one proposal-generation run.

This is the lineage object the Execution Report (`/report/[id]`) reconstructs and
the contribution metrics are derived from (ui-design.md §6.6, rag-design.md §6).
It links a run to the exact chunks it drew from each repository, the scores, the
stage timings, the gate verdicts, and — for refused runs — the refusal reason
with zero retrieval hits and no generation stages.

Pure record: it captures *what happened*, computed by the generation pipeline and
persisted immutably; it contains no behavior beyond simple derived views.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.domain.generation.enums import (
    GenerationGateVerdict,
    GenerationStage,
)
from app.domain.metrics.contribution import ContributionBreakdown
from app.domain.proposals.enums import ConfidenceBand, GenerationOutcome
from app.domain.repositories.repository import Repository


@dataclass(frozen=True, slots=True)
class RetrievalHit:
    """One retrieved candidate that entered the pool, with its score."""

    chunk_id: str
    doc_id: str
    repository: Repository
    score: float
    source_name: str
    page_start: int
    page_end: int


@dataclass(frozen=True, slots=True)
class Citation:
    """A grounded claim traced to its source evidence chunk.

    ``repository`` should always be ``FINANCIAL`` — citations may only resolve to
    the evidence repository. Any other value is, by definition, leakage.
    """

    claim_ordinal: int  # which grounded sentence/claim in the output
    chunk_id: str
    repository: Repository
    source_name: str
    page: int


@dataclass(frozen=True, slots=True)
class StageTiming:
    """Duration of one pipeline stage, summed to the headline generation time."""

    stage: GenerationStage
    duration_ms: int


@dataclass(frozen=True, slots=True)
class GateOutcome:
    """A guardrail decision recorded in lineage with its reason."""

    name: str  # e.g. "financial_grounding", "figure_retention", "factual_health"
    verdict: GenerationGateVerdict
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class GenerationEvent:
    """Immutable record of a single generation run (`PROPOSAL_GEN`)."""

    gen_id: str
    engagement_id: str
    prompt: str
    ts: datetime
    outcome: GenerationOutcome
    confidence: float
    confidence_band: ConfidenceBand
    retrieval_hits: tuple[RetrievalHit, ...] = ()
    citations: tuple[Citation, ...] = ()
    stage_timings: tuple[StageTiming, ...] = ()
    gate_outcomes: tuple[GateOutcome, ...] = ()
    contribution: ContributionBreakdown | None = None
    proposal_id: str | None = None  # set when a proposal was produced
    refusal_reason: str | None = None  # set when outcome is REFUSED
    # The exact policy snapshot used, for reproducibility (weights, thresholds).
    policy_fingerprint: str | None = None
    retrieval_weights: dict[Repository, float] = field(default_factory=dict)

    @property
    def is_refused(self) -> bool:
        return self.outcome is GenerationOutcome.REFUSED

    @property
    def total_duration_ms(self) -> int:
        """Headline generation time = the TOTAL stage, or the sum of stages."""
        for timing in self.stage_timings:
            if timing.stage is GenerationStage.TOTAL:
                return timing.duration_ms
        return sum(
            t.duration_ms for t in self.stage_timings if t.stage is not GenerationStage.TOTAL
        )
