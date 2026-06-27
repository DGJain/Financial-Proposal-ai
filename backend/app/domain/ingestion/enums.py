"""Ingestion-pipeline vocabulary: content kinds, routing/gate outcomes, status.

The quality-gate verdict reuses ``QualityGateVerdict`` from
``app.domain.generation.enums`` (APPROVED / RE_EXTRACT / HUMAN_REVIEW) — the
ingestion gate and the report surface speak the same words, so there is one
source of truth for that decision.
"""

from __future__ import annotations

from enum import StrEnum


class ContentType(StrEnum):
    """The atomic kind of a chunk's payload (drives chunking strategy).

    Financial chunking keeps each ``TABLE`` and ``FIGURE`` atomic and groups
    flowing prose into ``TEXT`` chunks (document-intelligence.md U-3).
    """

    TEXT = "text"
    TABLE = "table"
    FIGURE = "figure"


class IngestionStatus(StrEnum):
    """Terminal outcome of one ingestion run, surfaced to the caller/UI."""

    INDEXED = "indexed"  # embedded into repo_financial + cataloged
    SKIPPED_DUPLICATE = "skipped_duplicate"  # content_hash already ingested
    ROUTED_TO_REVIEW = "routed_to_review"  # gate failed / low confidence


class ReviewReason(StrEnum):
    """Why a document was routed to the human-review queue instead of indexed."""

    LOW_CLASSIFIER_CONFIDENCE = "low_classifier_confidence"
    QUALITY_GATE_FAILED = "quality_gate_failed"
    ANONYMIZATION_FAILED = "anonymization_failed"  # exemplar leaked engagement content
    NOT_CURATED = "not_curated"  # open upload tried to reach an approval-gated repo
