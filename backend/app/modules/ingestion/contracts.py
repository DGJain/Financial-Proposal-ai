"""Repository-agnostic ingestion contracts (the Phase 2 strategy seam).

Phase 1 hard-wired the financial path. Phase 2 generalizes ingestion to three
repositories whose handling differs only in four concerns — quality assessment,
the gate predicate, metadata extraction, and chunking (document-intelligence
U-3/U-4). These Protocols capture exactly those four concerns so the orchestrator
becomes repository-agnostic (open/closed): adding a repository means adding a
``RepositoryIngestionStrategy``, never editing the engine.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from app.domain.chunks.chunk import Chunk
from app.domain.chunks.quality import QualityScores
from app.domain.documents.acl import AccessControl
from app.domain.ingestion.extracted import ExtractedDocument
from app.domain.repositories.repository import Repository
from app.modules.ingestion.quality.gate import GateResult


@runtime_checkable
class RepositoryMetadata(Protocol):
    """Repository-specific layered metadata (U-2), in a uniform shape.

    ``subtype_value`` is stored on ``Document.subtype``; ``chunk_metadata`` is the
    filterable subset stamped onto every chunk's ChromaDB metadata.
    """

    @property
    def subtype_value(self) -> str: ...

    def chunk_metadata(self) -> dict[str, str | int]: ...


@runtime_checkable
class RepositoryIngestionStrategy(Protocol):
    """The per-repository handling bundle the engine dispatches to.

    ``assess`` measures quality (the engine stamps ``classification_confidence``
    onto the scores before gating, so the proposal soft gate can read it);
    ``gate`` turns scores into a verdict; ``extract_metadata`` derives the
    repository schema; ``chunk`` produces the repository's chunk shape.
    """

    @property
    def repository(self) -> Repository: ...

    def assess(self, document: ExtractedDocument) -> QualityScores: ...

    def gate(self, scores: QualityScores) -> GateResult: ...

    def extract_metadata(
        self,
        document: ExtractedDocument,
        *,
        hints: Mapping[str, str] | None = None,
    ) -> RepositoryMetadata: ...

    def chunk(
        self,
        document: ExtractedDocument,
        *,
        doc_id: str,
        access: AccessControl,
        metadata: RepositoryMetadata,
    ) -> list[Chunk]: ...
