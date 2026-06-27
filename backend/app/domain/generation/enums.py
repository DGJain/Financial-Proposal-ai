"""Generation-pipeline vocabulary: gate verdicts and stage timeline."""

from __future__ import annotations

from enum import StrEnum


class QualityGateVerdict(StrEnum):
    """Outcome of an ingestion quality gate (document-intelligence.md §8.7/U-4)."""

    APPROVED = "approved"
    RE_EXTRACT = "re_extract"
    HUMAN_REVIEW = "human_review"


class GenerationGateVerdict(StrEnum):
    """Outcome of a generation-time guardrail.

    Covers the financial grounding gate, the figure/entity-retention gate, and
    the factual-contribution health check (rag-design.md §5/§6b).
    """

    PASS = "pass"
    BLOCK_REGENERATE = "block_regenerate"  # figure leakage / failed retention
    REFUSE = "refuse"  # grounding below floor after loop exhaustion


class GenerationStage(StrEnum):
    """The five timeline stages on the Execution Report (ui-design.md §9).

    ``rewrite → retrieve → ground → generate``; ``TOTAL`` is the headline sum.
    """

    REWRITE = "rewrite"
    RETRIEVE = "retrieve"
    GROUND = "ground"
    GENERATE = "generate"
    TOTAL = "total"
