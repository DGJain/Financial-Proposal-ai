"""Wire DTOs for the Phase 5 analytics surface (report / history / metrics).

The frontend's generated client binds to these. They mirror the read use-case
result shapes but stay separate from the domain (the HTTP contract can evolve
independently), with ``from_domain`` factories keeping the mapping in one place.
Reuses the contribution / confidence DTOs from the generation schema so the two
surfaces share one vocabulary.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.api.schemas.generation import ConfidenceDTO, ContributionDTO, RepositoryShareDTO
from app.domain.generation.enums import GenerationStage, QualityGateVerdict
from app.domain.generation.generation_event import GenerationEvent, RetrievalHit
from app.domain.proposals.enums import GenerationOutcome
from app.domain.repositories.repository import Repository
from app.modules.metrics.generation_health.health import GenerationHealthData
from app.modules.metrics.repository_stats.stats import RepositoryMetricsData
from app.modules.reporting.execution_report import ExecutionReportData
from app.modules.reporting.history import AnalyticsRow
from app.modules.reporting.quality import FinancialQualityAggregate


# --- shared components --------------------------------------------------------


class RetrievalItemDTO(BaseModel):
    """One retrieved candidate with its relevance score (ui-design.md §5.C)."""

    chunk_id: str
    doc_id: str
    repository: Repository
    source_name: str
    score: float
    page_start: int
    page_end: int

    @classmethod
    def from_domain(cls, hit: RetrievalHit) -> RetrievalItemDTO:
        return cls(
            chunk_id=hit.chunk_id,
            doc_id=hit.doc_id,
            repository=hit.repository,
            source_name=hit.source_name,
            score=round(hit.score, 4),
            page_start=hit.page_start,
            page_end=hit.page_end,
        )


class StageTimingDTO(BaseModel):
    stage: GenerationStage
    duration_ms: int


class ReportCitationDTO(BaseModel):
    claim_ordinal: int
    source_name: str
    page: int


class QualityDTO(BaseModel):
    """Aggregated quality of a run's retrieved financial evidence (§6/7/8)."""

    ocr_confidence: float
    extraction_quality: float
    information_loss_pct: float
    gate_verdict: QualityGateVerdict
    document_count: int

    @classmethod
    def from_domain(cls, q: FinancialQualityAggregate) -> QualityDTO:
        return cls(
            ocr_confidence=q.ocr_confidence,
            extraction_quality=q.extraction_quality,
            information_loss_pct=q.information_loss_pct,
            gate_verdict=q.gate_verdict,
            document_count=q.document_count,
        )


# --- execution report (§6.6) -------------------------------------------------


def _hits_for(event: GenerationEvent, repository: Repository) -> list[RetrievalItemDTO]:
    return [
        RetrievalItemDTO.from_domain(h)
        for h in event.retrieval_hits
        if h.repository is repository
    ]


class ExecutionReportDTO(BaseModel):
    """Full forensic breakdown of one run — the 10 numbered sections."""

    gen_id: str
    prompt: str  # §1 verbatim prompt
    engagement_id: str
    timestamp: datetime
    outcome: GenerationOutcome
    confidence: ConfidenceDTO
    proposal_id: str | None = None  # set when a proposal was produced
    refusal_reason: str | None = None
    files_used: list[str] = Field(default_factory=list)  # §2 distinct sources
    retrieved_financial: list[RetrievalItemDTO] = Field(default_factory=list)  # §3
    retrieved_proposal: list[RetrievalItemDTO] = Field(default_factory=list)  # §4
    retrieved_template: list[RetrievalItemDTO] = Field(default_factory=list)  # §5
    quality: QualityDTO | None = None  # §6/7/8 OCR · extraction · info-loss + gate
    stages: list[StageTimingDTO] = Field(default_factory=list)  # §9 timeline
    total_duration_ms: int = 0
    citations: list[ReportCitationDTO] = Field(default_factory=list)  # §10
    contribution: ContributionDTO | None = None

    @classmethod
    def from_domain(cls, data: ExecutionReportData) -> ExecutionReportDTO:
        event = data.event
        files = list(dict.fromkeys(h.source_name for h in event.retrieval_hits))
        return cls(
            gen_id=event.gen_id,
            prompt=event.prompt,
            engagement_id=event.engagement_id,
            timestamp=event.ts,
            outcome=event.outcome,
            confidence=ConfidenceDTO(score=event.confidence, band=event.confidence_band),
            proposal_id=event.proposal_id,
            refusal_reason=event.refusal_reason,
            files_used=files,
            retrieved_financial=_hits_for(event, Repository.FINANCIAL),
            retrieved_proposal=_hits_for(event, Repository.PROPOSAL),
            retrieved_template=_hits_for(event, Repository.TEMPLATE),
            quality=QualityDTO.from_domain(data.quality) if data.quality else None,
            stages=[
                StageTimingDTO(stage=t.stage, duration_ms=t.duration_ms)
                for t in event.stage_timings
            ],
            total_duration_ms=event.total_duration_ms,
            citations=[
                ReportCitationDTO(
                    claim_ordinal=c.claim_ordinal, source_name=c.source_name, page=c.page
                )
                for c in event.citations
            ],
            contribution=(
                ContributionDTO.from_domain(event.contribution)
                if event.contribution is not None
                else None
            ),
        )


# --- prompt history (§5.A) ---------------------------------------------------


class AnalyticsRowDTO(BaseModel):
    """A nine-field history/analytics row; opens the Execution Report on click."""

    gen_id: str  # opens /report/[gen_id]
    proposal_id: str | None
    title: str  # the prompt
    timestamp: datetime
    files_used: int
    outcome: GenerationOutcome
    processing_time_s: float
    ocr_confidence: float | None = None  # "—" for refused runs
    extraction_quality: float | None = None
    information_loss_pct: float | None = None
    repository_contribution_pct: float  # financial share of assembled context

    @classmethod
    def from_domain(cls, row: AnalyticsRow) -> AnalyticsRowDTO:
        event = row.event
        q = row.quality
        contribution = (
            event.contribution.context_share.financial
            if event.contribution is not None
            else 0.0
        )
        distinct_files = len({h.doc_id for h in event.retrieval_hits})
        return cls(
            gen_id=event.gen_id,
            proposal_id=event.proposal_id,
            title=event.prompt,
            timestamp=event.ts,
            files_used=distinct_files,
            outcome=event.outcome,
            processing_time_s=round(event.total_duration_ms / 1000.0, 2),
            ocr_confidence=q.ocr_confidence if q else None,
            extraction_quality=q.extraction_quality if q else None,
            information_loss_pct=q.information_loss_pct if q else None,
            repository_contribution_pct=round(contribution, 2),
        )


class PromptHistoryDTO(BaseModel):
    rows: list[AnalyticsRowDTO] = Field(default_factory=list)
    limit: int
    offset: int


# --- repository metrics (§6.7) -----------------------------------------------


class RepositoryMetricsDTO(BaseModel):
    """The five repo cards + corpus composition triple."""

    financial_documents: int
    proposal_examples: int
    templates: int
    embedded_chunks: int
    last_ingestion_ts: datetime | None = None
    corpus_contribution: RepositoryShareDTO

    @classmethod
    def from_domain(cls, data: RepositoryMetricsData) -> RepositoryMetricsDTO:
        return cls(
            financial_documents=data.financial_documents,
            proposal_examples=data.proposal_examples,
            templates=data.templates,
            embedded_chunks=data.embedded_chunks,
            last_ingestion_ts=data.last_ingestion_ts,
            corpus_contribution=RepositoryShareDTO.from_domain(data.corpus_contribution),
        )


# --- generation health (Page 4 §2) -------------------------------------------


class DailyBarDTO(BaseModel):
    day: str  # ISO date
    generated: int
    refused: int


class InfoLossBucketDTO(BaseModel):
    label: str
    count: int


class GenerationHealthDTO(BaseModel):
    window_days: int
    runs_total: int
    proposals_generated: int
    refusal_rate: float
    avg_confidence: float
    avg_extraction_quality: float
    daily: list[DailyBarDTO] = Field(default_factory=list)
    info_loss_distribution: list[InfoLossBucketDTO] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, data: GenerationHealthData) -> GenerationHealthDTO:
        return cls(
            window_days=data.window_days,
            runs_total=data.runs_total,
            proposals_generated=data.proposals_generated,
            refusal_rate=data.refusal_rate,
            avg_confidence=data.avg_confidence,
            avg_extraction_quality=data.avg_extraction_quality,
            daily=[
                DailyBarDTO(day=b.day.isoformat(), generated=b.generated, refused=b.refused)
                for b in data.daily
            ],
            info_loss_distribution=[
                InfoLossBucketDTO(label=b.label, count=b.count)
                for b in data.info_loss_distribution
            ],
        )
