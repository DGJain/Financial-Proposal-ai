"""Template ingestion strategy — the scaffold-corpus handling bundle."""

from __future__ import annotations

from collections.abc import Mapping

from app.core.policies.quality_gates import QualityGatePolicy
from app.domain.chunks.chunk import Chunk
from app.domain.chunks.quality import QualityScores
from app.domain.documents.acl import AccessControl
from app.domain.ingestion.extracted import ExtractedDocument
from app.domain.repositories.repository import Repository
from app.modules.ingestion.chunking.template import TemplateChunker
from app.modules.ingestion.contracts import RepositoryMetadata
from app.modules.ingestion.metadata.template import TemplateMetadataExtractor
from app.modules.ingestion.quality.gate import GateResult, TemplateQualityGate
from app.modules.ingestion.quality.template_assessor import TemplateQualityAssessor


class TemplateStrategy:
    """``RepositoryIngestionStrategy`` for ``repo_templates`` (structural scaffold)."""

    repository = Repository.TEMPLATE

    def __init__(self, embedding_model_version: str, policy: QualityGatePolicy) -> None:
        self._assessor = TemplateQualityAssessor(weights=policy.template_weights)
        self._gate = TemplateQualityGate(predicate=policy.template_gate)
        self._metadata = TemplateMetadataExtractor()
        self._chunker = TemplateChunker(embedding_model_version=embedding_model_version)

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
