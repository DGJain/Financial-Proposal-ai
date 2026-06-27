"""Join a generation run to the quality of its retrieved financial documents.

OCR confidence, extraction quality (EQS) and information-loss are *per-document
ingestion* metrics — they live on ``IngestionLineage.quality`` (the
``document_quality`` row), not on the ``GenerationEvent``. The Execution Report
(§6/7/8) and the Prompt-History rows surface them at the *run* level, so we join
each run's **financial** retrieval hits back to their source documents' quality
and take the mean across them (the chosen aggregation; refused runs and runs that
retrieved no financial evidence have no aggregate). Reads are batched
(``get_many``) so a page of history never fans out into N+1 queries.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from statistics import fmean

from app.domain.generation.enums import QualityGateVerdict
from app.domain.generation.generation_event import GenerationEvent
from app.domain.ingestion.lineage import IngestionLineage
from app.domain.ports.ingestion_lineage import IngestionLineagePort
from app.domain.repositories.repository import Repository


@dataclass(frozen=True, slots=True)
class FinancialQualityAggregate:
    """Mean ingestion quality across a run's retrieved financial documents."""

    ocr_confidence: float
    extraction_quality: float  # mean EQS
    information_loss_pct: float  # mean (1 − EQS) · 100
    gate_verdict: QualityGateVerdict
    document_count: int


def financial_doc_ids(event: GenerationEvent) -> list[str]:
    """Distinct financial source-document ids that entered the run's pool."""
    seen: dict[str, None] = {}
    for hit in event.retrieval_hits:
        if hit.repository is Repository.FINANCIAL:
            seen.setdefault(hit.doc_id, None)
    return list(seen)


def aggregate_from_records(
    event: GenerationEvent,
    records: Mapping[str, IngestionLineage],
) -> FinancialQualityAggregate | None:
    """Aggregate using a pre-fetched lineage mapping (no I/O)."""
    qualities = []
    verdicts = []
    for doc_id in financial_doc_ids(event):
        record = records.get(doc_id)
        if record is not None:
            qualities.append(record.quality)
            verdicts.append(record.gate_verdict)
    if not qualities:
        return None
    mean_eqs = fmean(q.eqs for q in qualities)
    # Aggregate gate verdict: APPROVED only if every retrieved doc passed; the
    # first non-approving verdict otherwise (the run leaned on a flagged doc).
    verdict = next(
        (v for v in verdicts if v is not QualityGateVerdict.APPROVED),
        QualityGateVerdict.APPROVED,
    )
    return FinancialQualityAggregate(
        ocr_confidence=round(fmean(q.ocr_confidence for q in qualities), 4),
        extraction_quality=round(mean_eqs, 4),
        information_loss_pct=round((1.0 - mean_eqs) * 100.0, 2),
        gate_verdict=verdict,
        document_count=len(qualities),
    )


async def aggregate_financial_quality(
    event: GenerationEvent,
    lineage: IngestionLineagePort,
) -> FinancialQualityAggregate | None:
    """Fetch + aggregate quality for one run's financial documents."""
    doc_ids = financial_doc_ids(event)
    if not doc_ids:
        return None
    records = await lineage.get_many(doc_ids)
    return aggregate_from_records(event, records)


async def aggregate_many(
    events: Sequence[GenerationEvent],
    lineage: IngestionLineagePort,
) -> dict[str, FinancialQualityAggregate | None]:
    """Aggregate quality for a page of runs in a single batched lineage read."""
    all_ids = {doc_id for event in events for doc_id in financial_doc_ids(event)}
    records = await lineage.get_many(sorted(all_ids)) if all_ids else {}
    return {event.gen_id: aggregate_from_records(event, records) for event in events}
