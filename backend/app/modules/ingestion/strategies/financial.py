"""Financial ingestion strategy — the evidence-corpus handling bundle."""

from __future__ import annotations

from collections.abc import Mapping

from app.core.policies.quality_gates import QualityGatePolicy
from app.domain.chunks.chunk import Chunk
from app.domain.chunks.quality import QualityScores
from app.domain.documents.acl import AccessControl
from app.domain.ingestion.extracted import ExtractedDocument
from app.domain.repositories.repository import Repository
from app.modules.ingestion.chunking.financial import FinancialChunker
from app.modules.ingestion.contracts import RepositoryMetadata
from app.modules.ingestion.metadata.financial import FinancialMetadataExtractor
from app.modules.ingestion.quality.assessor import FinancialQualityAssessor
from app.modules.ingestion.quality.gate import FinancialQualityGate, GateResult


class FinancialStrategy:
    """``RepositoryIngestionStrategy`` for ``repo_financial`` (citable evidence)."""

    repository = Repository.FINANCIAL

    def __init__(self, embedding_model_version: str, policy: QualityGatePolicy) -> None:
        self._assessor = FinancialQualityAssessor(weights=policy.financial_weights)
        self._gate = FinancialQualityGate(predicate=policy.financial_gate)
        self._metadata = FinancialMetadataExtractor()
        self._chunker = FinancialChunker(embedding_model_version=embedding_model_version)

    def assess(self, document: ExtractedDocument) -> QualityScores:
        return self._assessor.assess(document)

    def gate(self, scores: QualityScores) -> GateResult:
        return self._gate.evaluate(scores)

    def extract_metadata(
        self, document: ExtractedDocument, *, hints: Mapping[str, str] | None = None
    ) -> RepositoryMetadata:
        return self._metadata.extract(document, hints=hints)

    def chunk(
        self,
        document: ExtractedDocument,
        *,
        doc_id: str,
        access: AccessControl,
        metadata: RepositoryMetadata,
    ) -> list[Chunk]:
        return self._chunker.chunk(document, doc_id=doc_id, access=access, metadata=metadata)
