"""Chunk entity — the unit of retrieval, embedded into one ChromaDB collection.

Chunking is repository-specific (document-intelligence.md U-3): financial chunks
keep tables atomic and carry a fiscal period; proposal chunks are section-
semantic; template chunks preserve placeholder slots verbatim. The entity is
common, with repository-specific fields carried in ``metadata`` (which becomes
filterable ChromaDB metadata).

Every chunk copies its parent document's ``AccessControl`` so retrieval can
ACL-pre-filter without a join, and records ``embedding_model_version`` so a
collection's vectors are only ever compared within one embedding model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.documents.acl import AccessControl
from app.domain.repositories.repository import Repository, RoleInGeneration


@dataclass(frozen=True, slots=True)
class ChunkSpan:
    """Source location of a chunk, for citation back to ``source · page``."""

    page_start: int
    page_end: int
    bbox: tuple[float, float, float, float] | None = None  # x0,y0,x1,y1 if known


@dataclass(frozen=True, slots=True)
class Chunk:
    """A retrievable, embedded fragment of a document."""

    chunk_id: str
    doc_id: str
    repository: Repository
    role_in_generation: RoleInGeneration
    text: str
    ordinal: int  # position within the source document
    span: ChunkSpan
    access: AccessControl
    embedding_model_version: str
    vector_id: str | None = None  # ChromaDB vector id once indexed
    # Repository-specific filterable metadata (e.g. fiscal_year, section_label,
    # section_slot). Kept open so each chunking strategy can attach its schema.
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_citable(self) -> bool:
        """Only evidence (financial) chunks may become citations (hard rule)."""
        return self.role_in_generation is RoleInGeneration.EVIDENCE
