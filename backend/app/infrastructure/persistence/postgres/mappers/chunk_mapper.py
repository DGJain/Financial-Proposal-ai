"""Translation between the ``Chunk`` domain entity and ``DocumentChunkRow``.

Keeps the catalog row in sync with the vector stored in ChromaDB: same id, same
copied ACL, same span. Enums are persisted as their string values; the bbox tuple
and ACL group set are stored as JSON and reconstructed on read.
"""

from __future__ import annotations

from app.domain.chunks.chunk import Chunk, ChunkSpan
from app.domain.documents.acl import AccessControl
from app.domain.repositories.repository import Repository, RoleInGeneration
from app.infrastructure.persistence.postgres.models.document import DocumentChunkRow


def to_row(chunk: Chunk) -> DocumentChunkRow:
    return DocumentChunkRow(
        chunk_id=chunk.chunk_id,
        doc_id=chunk.doc_id,
        repository=chunk.repository.value,
        role_in_generation=chunk.role_in_generation.value,
        text=chunk.text,
        ordinal=chunk.ordinal,
        page_start=chunk.span.page_start,
        page_end=chunk.span.page_end,
        bbox=list(chunk.span.bbox) if chunk.span.bbox is not None else None,
        embedding_model_version=chunk.embedding_model_version,
        vector_id=chunk.vector_id,
        chunk_metadata=dict(chunk.metadata),
        acl_groups=sorted(chunk.access.acl_groups),
        engagement_id=chunk.access.engagement_id,
        classification=chunk.access.classification,
    )


def to_domain(row: DocumentChunkRow) -> Chunk:
    bbox = tuple(row.bbox) if row.bbox is not None else None
    return Chunk(
        chunk_id=row.chunk_id,
        doc_id=row.doc_id,
        repository=Repository(row.repository),
        role_in_generation=RoleInGeneration(row.role_in_generation),
        text=row.text,
        ordinal=row.ordinal,
        span=ChunkSpan(
            page_start=row.page_start,
            page_end=row.page_end,
            bbox=bbox,  # type: ignore[arg-type]
        ),
        access=AccessControl(
            acl_groups=frozenset(row.acl_groups),
            engagement_id=row.engagement_id,
            classification=row.classification,
        ),
        embedding_model_version=row.embedding_model_version,
        vector_id=row.vector_id,
        metadata=dict(row.chunk_metadata),
    )
