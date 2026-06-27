"""Auditable ingestion records — what the pipeline decided, recorded immutably.

``IngestionLineage`` is the per-document audit trail the platform persists
alongside the catalog row: the classifier distribution and confidence, the
repo-aware quality scores, the gate verdict, and a *reference* to the redaction
ledger (never the redacted values). It makes every ingestion decision replayable
against the exact policy snapshot that produced it (``policy_fingerprint``).

``HumanReviewItem`` is what gets queued when the gate fails or the classifier is
unsure, and ``IngestionResult`` is the value returned to the caller/API.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.domain.chunks.quality import QualityScores
from app.domain.documents.enums import SensitivityFlag
from app.domain.generation.enums import QualityGateVerdict
from app.domain.ingestion.enums import IngestionStatus, ReviewReason
from app.domain.repositories.repository import Repository, SoftDistribution


@dataclass(frozen=True, slots=True)
class IngestionLineage:
    """Immutable per-document ingestion audit record (the ``document_quality`` row)."""

    doc_id: str
    repository: Repository
    soft_distribution: SoftDistribution
    classification_confidence: float
    quality: QualityScores
    gate_verdict: QualityGateVerdict
    embedding_model_version: str
    chunk_count: int
    ingestion_ts: datetime
    redaction_ledger_uri: str | None = None
    redaction_counts: dict[str, int] = field(default_factory=dict)
    sensitivity: frozenset[SensitivityFlag] = field(default_factory=frozenset)
    policy_fingerprint: str | None = None


@dataclass(frozen=True, slots=True)
class HumanReviewItem:
    """A document parked for an analyst because it could not be auto-indexed."""

    doc_id: str
    reason: ReviewReason
    gate_verdict: QualityGateVerdict
    quality: QualityScores
    soft_distribution: SoftDistribution
    classification_confidence: float
    source_uri: str
    queued_ts: datetime
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class IngestionResult:
    """Outcome of one ``IngestFinancialDocument`` invocation."""

    status: IngestionStatus
    doc_id: str
    repository: Repository = Repository.FINANCIAL
    chunk_count: int = 0
    gate_verdict: QualityGateVerdict | None = None
    quality: QualityScores | None = None
    review_reason: ReviewReason | None = None

    @property
    def indexed(self) -> bool:
        return self.status is IngestionStatus.INDEXED
