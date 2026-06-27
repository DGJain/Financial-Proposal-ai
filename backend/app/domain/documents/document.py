"""Document entity — the catalog record for an ingested source file.

One ``Document`` is the unit the ingestion pipeline produces: an extracted,
classified, quality-scored source that has been routed to exactly one primary
repository (section-split routing may additionally emit child documents). It is
the PostgreSQL catalog's system-of-record shape, carrying the layered base
metadata from document-intelligence.md U-2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.domain.documents.acl import AccessControl
from app.domain.documents.enums import FileType, SensitivityFlag
from app.domain.repositories.repository import Repository, SoftDistribution


@dataclass(frozen=True, slots=True)
class Provenance:
    """Where a document came from and basic extracted facts about it."""

    source_uri: str  # object-storage URI of the raw original
    file_type: FileType
    ingestion_ts: datetime
    page_count: int
    language: str
    content_hash: str  # stable identity for dedup / re-ingestion idempotency


@dataclass(frozen=True, slots=True)
class Document:
    """An ingested, classified document catalog record.

    ``quality`` and ``subtype`` are set after the gate; ``lineage_root`` points
    into the immutable audit log so classification/π_d/gate decisions are
    replayable. ``quality`` is intentionally a forward reference shape held by
    the catalog (see ``app.domain.chunks.quality.QualityScores``) and is attached
    once the repo-aware gate has run.
    """

    doc_id: str
    repository: Repository
    subtype: str  # one of the per-repository subtype enums (stored as its value)
    provenance: Provenance
    access: AccessControl
    soft_distribution: SoftDistribution
    repo_confidence: float
    sensitivity: frozenset[SensitivityFlag] = field(default_factory=frozenset)
    object_uri_versioned: str | None = None  # versioned copy, if retained
    lineage_root: str | None = None
    parent_doc_id: str | None = None  # set for section-split child documents
    version: int = 1

    @property
    def is_split_child(self) -> bool:
        """True if this document was produced by section-level split routing."""
        return self.parent_doc_id is not None
