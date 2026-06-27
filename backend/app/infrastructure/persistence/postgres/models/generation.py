"""Generation-lineage ORM models — the immutable audit trail.

One ``generation_events`` row per run links to four append-only child tables that
let the Execution Report (`/report/[id]`) be reconstructed exactly: retrieval
hits (with scores), citations (source · page), stage timings, and gate outcomes.
Contribution percentages are stored as columns so dashboard aggregates are plain
SQL. These tables are written once and never updated (enforced by the adapter).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.persistence.postgres.base import Base


class GenerationEventRow(Base):
    __tablename__ = "generation_events"

    gen_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    engagement_id: Mapped[str] = mapped_column(String(64), index=True)
    prompt: Mapped[str] = mapped_column(Text)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    outcome: Mapped[str] = mapped_column(String(16), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    confidence_band: Mapped[str] = mapped_column(String(8))

    proposal_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    refusal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    retrieval_weights: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)

    # Contribution % (0-100) — context & factual families (rag-design.md §6b)
    ctx_financial_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    ctx_proposal_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    ctx_template_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    fact_financial_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    fact_proposal_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    fact_template_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    retrieval_hits: Mapped[list[RetrievalHitRow]] = relationship(
        back_populates="event", cascade="all, delete-orphan", order_by="RetrievalHitRow.id"
    )
    citations: Mapped[list[CitationRow]] = relationship(
        back_populates="event", cascade="all, delete-orphan", order_by="CitationRow.id"
    )
    stage_timings: Mapped[list[StageTimingRow]] = relationship(
        back_populates="event", cascade="all, delete-orphan", order_by="StageTimingRow.id"
    )
    gate_outcomes: Mapped[list[GateOutcomeRow]] = relationship(
        back_populates="event", cascade="all, delete-orphan", order_by="GateOutcomeRow.id"
    )


class RetrievalHitRow(Base):
    __tablename__ = "retrieval_hits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    gen_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("generation_events.gen_id"), index=True
    )
    chunk_id: Mapped[str] = mapped_column(String(64))
    doc_id: Mapped[str] = mapped_column(String(64))
    repository: Mapped[str] = mapped_column(String(16), index=True)
    score: Mapped[float] = mapped_column(Float)
    source_name: Mapped[str] = mapped_column(String(256))
    page_start: Mapped[int] = mapped_column(Integer)
    page_end: Mapped[int] = mapped_column(Integer)

    event: Mapped[GenerationEventRow] = relationship(back_populates="retrieval_hits")


class CitationRow(Base):
    __tablename__ = "citations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    gen_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("generation_events.gen_id"), index=True
    )
    claim_ordinal: Mapped[int] = mapped_column(Integer)
    chunk_id: Mapped[str] = mapped_column(String(64))
    repository: Mapped[str] = mapped_column(String(16))
    source_name: Mapped[str] = mapped_column(String(256))
    page: Mapped[int] = mapped_column(Integer)

    event: Mapped[GenerationEventRow] = relationship(back_populates="citations")


class StageTimingRow(Base):
    __tablename__ = "stage_timings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    gen_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("generation_events.gen_id"), index=True
    )
    stage: Mapped[str] = mapped_column(String(16))
    duration_ms: Mapped[int] = mapped_column(Integer)

    event: Mapped[GenerationEventRow] = relationship(back_populates="stage_timings")


class GateOutcomeRow(Base):
    __tablename__ = "gate_outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    gen_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("generation_events.gen_id"), index=True
    )
    name: Mapped[str] = mapped_column(String(32))
    verdict: Mapped[str] = mapped_column(String(20))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    event: Mapped[GenerationEventRow] = relationship(back_populates="gate_outcomes")
