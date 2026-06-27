"""Translation between ``GenerationEvent`` (+ children) and its ORM rows.

The event aggregate maps to one parent row plus four child collections. On read,
the children are re-sorted into deterministic order so the Execution Report is
reconstructed identically every time.
"""

from __future__ import annotations

from app.domain.generation.enums import (
    GenerationGateVerdict,
    GenerationStage,
)
from app.domain.generation.generation_event import (
    Citation,
    GateOutcome,
    GenerationEvent,
    RetrievalHit,
    StageTiming,
)
from app.domain.metrics.contribution import ContributionBreakdown, RepositoryShare
from app.domain.proposals.enums import ConfidenceBand, GenerationOutcome
from app.domain.repositories.repository import Repository
from app.infrastructure.persistence.postgres.models.generation import (
    CitationRow,
    GateOutcomeRow,
    GenerationEventRow,
    RetrievalHitRow,
    StageTimingRow,
)


def to_row(event: GenerationEvent) -> GenerationEventRow:
    row = GenerationEventRow(
        gen_id=event.gen_id,
        engagement_id=event.engagement_id,
        prompt=event.prompt,
        ts=event.ts,
        outcome=event.outcome.value,
        confidence=event.confidence,
        confidence_band=event.confidence_band.value,
        proposal_id=event.proposal_id,
        refusal_reason=event.refusal_reason,
        policy_fingerprint=event.policy_fingerprint,
        retrieval_weights={repo.value: w for repo, w in event.retrieval_weights.items()},
    )
    if event.contribution is not None:
        ctx = event.contribution.context_share
        fact = event.contribution.factual_share
        row.ctx_financial_pct = ctx.financial
        row.ctx_proposal_pct = ctx.proposal
        row.ctx_template_pct = ctx.template
        row.fact_financial_pct = fact.financial
        row.fact_proposal_pct = fact.proposal
        row.fact_template_pct = fact.template

    row.retrieval_hits = [
        RetrievalHitRow(
            chunk_id=h.chunk_id,
            doc_id=h.doc_id,
            repository=h.repository.value,
            score=h.score,
            source_name=h.source_name,
            page_start=h.page_start,
            page_end=h.page_end,
        )
        for h in event.retrieval_hits
    ]
    row.citations = [
        CitationRow(
            claim_ordinal=c.claim_ordinal,
            chunk_id=c.chunk_id,
            repository=c.repository.value,
            source_name=c.source_name,
            page=c.page,
        )
        for c in event.citations
    ]
    row.stage_timings = [
        StageTimingRow(stage=t.stage.value, duration_ms=t.duration_ms)
        for t in event.stage_timings
    ]
    row.gate_outcomes = [
        GateOutcomeRow(name=g.name, verdict=g.verdict.value, detail=g.detail)
        for g in event.gate_outcomes
    ]
    return row


def _contribution(row: GenerationEventRow) -> ContributionBreakdown | None:
    if row.ctx_financial_pct is None or row.fact_financial_pct is None:
        return None
    return ContributionBreakdown(
        context_share=RepositoryShare(
            financial=row.ctx_financial_pct,
            proposal=row.ctx_proposal_pct or 0.0,
            template=row.ctx_template_pct or 0.0,
        ),
        factual_share=RepositoryShare(
            financial=row.fact_financial_pct,
            proposal=row.fact_proposal_pct or 0.0,
            template=row.fact_template_pct or 0.0,
        ),
    )


def to_domain(row: GenerationEventRow) -> GenerationEvent:
    return GenerationEvent(
        gen_id=row.gen_id,
        engagement_id=row.engagement_id,
        prompt=row.prompt,
        ts=row.ts,
        outcome=GenerationOutcome(row.outcome),
        confidence=row.confidence,
        confidence_band=ConfidenceBand(row.confidence_band),
        retrieval_hits=tuple(
            RetrievalHit(
                chunk_id=h.chunk_id,
                doc_id=h.doc_id,
                repository=Repository(h.repository),
                score=h.score,
                source_name=h.source_name,
                page_start=h.page_start,
                page_end=h.page_end,
            )
            for h in row.retrieval_hits
        ),
        citations=tuple(
            Citation(
                claim_ordinal=c.claim_ordinal,
                chunk_id=c.chunk_id,
                repository=Repository(c.repository),
                source_name=c.source_name,
                page=c.page,
            )
            for c in row.citations
        ),
        stage_timings=tuple(
            StageTiming(stage=GenerationStage(t.stage), duration_ms=t.duration_ms)
            for t in row.stage_timings
        ),
        gate_outcomes=tuple(
            GateOutcome(
                name=g.name,
                verdict=GenerationGateVerdict(g.verdict),
                detail=g.detail,
            )
            for g in row.gate_outcomes
        ),
        contribution=_contribution(row),
        proposal_id=row.proposal_id,
        refusal_reason=row.refusal_reason,
        policy_fingerprint=row.policy_fingerprint,
        retrieval_weights={Repository(k): v for k, v in row.retrieval_weights.items()},
    )
