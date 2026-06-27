"""Proposal ingestion strategy — the exemplar-corpus handling bundle.

Section Coverage needs the proposal subtype, but the gate runs before metadata
extraction (U-1 ordering), so the strategy detects the subtype up front and feeds
it to the assessor.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.core.policies.quality_gates import QualityGatePolicy
from app.domain.chunks.chunk import Chunk
from app.domain.chunks.quality import QualityScores
from app.domain.documents.acl import AccessControl
from app.domain.ingestion.extracted import ExtractedDocument
from app.domain.repositories.repository import Repository
from app.modules.ingestion.chunking.proposal import ProposalChunker
from app.modules.ingestion.contracts import RepositoryMetadata
from app.modules.ingestion.metadata.proposal import ProposalMetadataExtractor
from app.modules.ingestion.quality.gate import GateResult, ProposalQualityGate
from app.modules.ingestion.quality.proposal_assessor import ProposalQualityAssessor


class ProposalStrategy:
    """``RepositoryIngestionStrategy`` for ``repo_proposals`` (style exemplars)."""

    repository = Repository.PROPOSAL

    def __init__(self, embedding_model_version: str, policy: QualityGatePolicy) -> None:
        self._assessor = ProposalQualityAssessor(weights=policy.proposal_weights)
        self._gate = ProposalQualityGate(predicate=policy.proposal_gate)
        self._metadata = ProposalMetadataExtractor()
        self._chunker = ProposalChunker(embedding_model_version=embedding_model_version)

    def assess(self, document: ExtractedDocument) -> QualityScores:
        subtype = self._metadata.detect_subtype(document)
        return self._assessor.assess(document, subtype=subtype)

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
