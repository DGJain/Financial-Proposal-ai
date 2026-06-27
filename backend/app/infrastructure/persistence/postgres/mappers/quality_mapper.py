"""Translation between ``IngestionLineage`` and ``DocumentQualityRow``.

Flattens the classifier distribution and quality value objects into scalar
columns for slicing/aggregation, and reconstructs them on read. The redaction
ledger is referenced by URI only.
"""

from __future__ import annotations

from app.domain.chunks.quality import QualityScores
from app.domain.documents.enums import SensitivityFlag
from app.domain.generation.enums import QualityGateVerdict
from app.domain.ingestion.lineage import IngestionLineage
from app.domain.repositories.repository import Repository, SoftDistribution
from app.infrastructure.persistence.postgres.models.document import DocumentQualityRow


def to_row(lineage: IngestionLineage) -> DocumentQualityRow:
    pi = lineage.soft_distribution
    q = lineage.quality
    return DocumentQualityRow(
        doc_id=lineage.doc_id,
        repository=lineage.repository.value,
        pi_financial=pi.financial,
        pi_proposal=pi.proposal,
        pi_template=pi.template,
        classification_confidence=lineage.classification_confidence,
        eqs=q.eqs,
        ocr_confidence=q.ocr_confidence,
        cfr=q.cfr,
        rpr=q.rpr,
        has_critical_low_confidence_region=q.has_critical_low_confidence_region,
        section_coverage=q.section_coverage,
        placeholder_integrity=q.placeholder_integrity,
        structural_fidelity=q.structural_fidelity,
        gate_verdict=lineage.gate_verdict.value,
        embedding_model_version=lineage.embedding_model_version,
        chunk_count=lineage.chunk_count,
        ingestion_ts=lineage.ingestion_ts,
        redaction_ledger_uri=lineage.redaction_ledger_uri,
        redaction_counts=dict(lineage.redaction_counts),
        sensitivity=sorted(flag.value for flag in lineage.sensitivity),
        policy_fingerprint=lineage.policy_fingerprint,
    )


def to_domain(row: DocumentQualityRow) -> IngestionLineage:
    return IngestionLineage(
        doc_id=row.doc_id,
        repository=Repository(row.repository),
        soft_distribution=SoftDistribution(
            financial=row.pi_financial,
            proposal=row.pi_proposal,
            template=row.pi_template,
        ),
        classification_confidence=row.classification_confidence,
        quality=QualityScores(
            eqs=row.eqs,
            ocr_confidence=row.ocr_confidence,
            cfr=row.cfr,
            rpr=row.rpr,
            has_critical_low_confidence_region=row.has_critical_low_confidence_region,
            section_coverage=row.section_coverage,
            placeholder_integrity=row.placeholder_integrity,
            structural_fidelity=row.structural_fidelity,
        ),
        gate_verdict=QualityGateVerdict(row.gate_verdict),
        embedding_model_version=row.embedding_model_version,
        chunk_count=row.chunk_count,
        ingestion_ts=row.ingestion_ts,
        redaction_ledger_uri=row.redaction_ledger_uri,
        redaction_counts=dict(row.redaction_counts),
        sensitivity=frozenset(SensitivityFlag(s) for s in row.sensitivity),
        policy_fingerprint=row.policy_fingerprint,
    )
