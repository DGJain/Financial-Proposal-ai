"""Catalog ORM models: documents and their chunks.

PostgreSQL is the catalog system of record, keyed by ``repository`` + ``subtype``
(architecture.md §6). ``content_hash`` is uniquely indexed to back re-ingestion
idempotency. ``document_chunks`` holds the ``chunk_id <-> vector_id`` mapping to
ChromaDB and copies each chunk's ACL so retrieval lineage needs no join.

Note: the ``document_chunks`` table is created now for data-plane cohesion; its
read/write adapter arrives with the ingestion phase (no ChunkCatalogPort yet).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.persistence.postgres.base import Base


class DocumentRow(Base):
    __tablename__ = "documents"

    doc_id: Mapped[str] = mapped_column(String(64), primary_key=True)

    # Classification / routing
    repository: Mapped[str] = mapped_column(String(16), index=True)
    subtype: Mapped[str] = mapped_column(String(64), index=True)
    pi_financial: Mapped[float] = mapped_column(Float)
    pi_proposal: Mapped[float] = mapped_column(Float)
    pi_template: Mapped[float] = mapped_column(Float)
    repo_confidence: Mapped[float] = mapped_column(Float)

    # Provenance
    source_uri: Mapped[str] = mapped_column(String(512))
    file_type: Mapped[str] = mapped_column(String(8))
    ingestion_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    page_count: Mapped[int] = mapped_column(Integer)
    language: Mapped[str] = mapped_column(String(16))
    content_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)

    # Access control (carried into retrieval pre-filters)
    acl_groups: Mapped[list[str]] = mapped_column(JSON, default=list)
    engagement_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    classification: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Sensitivity + lineage
    sensitivity: Mapped[list[str]] = mapped_column(JSON, default=list)
    object_uri_versioned: Mapped[str | None] = mapped_column(String(512), nullable=True)
    lineage_root: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parent_doc_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("documents.doc_id"), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1)

    chunks: Mapped[list[DocumentChunkRow]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    # One-to-one with the quality/lineage row. Declared so the unit-of-work knows
    # the FK dependency and always inserts the parent ``documents`` row before its
    # ``document_quality`` child — required by databases that enforce foreign keys
    # at flush time (PostgreSQL), which SQLite-off-by-default tests do not exercise.
    quality: Mapped[DocumentQualityRow | None] = relationship(
        back_populates="document", uselist=False
    )


class DocumentChunkRow(Base):
    __tablename__ = "document_chunks"

    chunk_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    doc_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("documents.doc_id"), index=True
    )
    repository: Mapped[str] = mapped_column(String(16), index=True)
    role_in_generation: Mapped[str] = mapped_column(String(16))

    text: Mapped[str] = mapped_column(Text)
    ordinal: Mapped[int] = mapped_column(Integer)
    page_start: Mapped[int] = mapped_column(Integer)
    page_end: Mapped[int] = mapped_column(Integer)
    bbox: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)

    embedding_model_version: Mapped[str] = mapped_column(String(64))
    vector_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    chunk_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)

    # Copied ACL (denormalized for filter-without-join)
    acl_groups: Mapped[list[str]] = mapped_column(JSON, default=list)
    engagement_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    classification: Mapped[str | None] = mapped_column(String(32), nullable=True)

    document: Mapped[DocumentRow] = relationship(back_populates="chunks")


class DocumentQualityRow(Base):
    """Per-document ingestion lineage: the gate decision and the numbers behind it.

    One row per ingested document (1:1 with ``documents``). Records the classifier
    distribution + confidence, the financial quality scores, the gate verdict, and
    a *reference* to the redaction ledger (the ledger blob lives in object storage)
    — making each ingestion replayable against its ``policy_fingerprint``.
    """

    __tablename__ = "document_quality"

    doc_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("documents.doc_id"), primary_key=True
    )
    repository: Mapped[str] = mapped_column(String(16), index=True)

    # Classifier distribution (π_d) + confidence.
    pi_financial: Mapped[float] = mapped_column(Float)
    pi_proposal: Mapped[float] = mapped_column(Float)
    pi_template: Mapped[float] = mapped_column(Float)
    classification_confidence: Mapped[float] = mapped_column(Float)

    # Quality scores (superset across repositories; only the relevant ones set).
    eqs: Mapped[float] = mapped_column(Float)
    ocr_confidence: Mapped[float] = mapped_column(Float)
    cfr: Mapped[float | None] = mapped_column(Float, nullable=True)  # financial
    rpr: Mapped[float | None] = mapped_column(Float, nullable=True)  # financial
    has_critical_low_confidence_region: Mapped[bool] = mapped_column(Boolean, default=False)
    section_coverage: Mapped[float | None] = mapped_column(Float, nullable=True)  # proposal
    placeholder_integrity: Mapped[float | None] = mapped_column(Float, nullable=True)  # template
    structural_fidelity: Mapped[float | None] = mapped_column(Float, nullable=True)  # template

    gate_verdict: Mapped[str] = mapped_column(String(20), index=True)
    embedding_model_version: Mapped[str] = mapped_column(String(64))
    chunk_count: Mapped[int] = mapped_column(Integer)
    ingestion_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # Redaction (reference only — never the redacted values).
    redaction_ledger_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)
    redaction_counts: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    sensitivity: Mapped[list[str]] = mapped_column(JSON, default=list)
    policy_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)

    document: Mapped[DocumentRow] = relationship(back_populates="quality")
