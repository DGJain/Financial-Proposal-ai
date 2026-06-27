"""Chunk-catalog port — PostgreSQL record of every embedded chunk.

Mirrors the vectors held in ChromaDB: one row per chunk carrying the
``chunk_id ↔ vector_id`` mapping and the chunk's copied ACL, so retrieval lineage
and re-ingestion supersede do not need to round-trip the vector store. Written in
the same Unit of Work as the parent ``Document`` (atomic catalog write).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from app.domain.chunks.chunk import Chunk
from app.domain.repositories.repository import Repository


@runtime_checkable
class ChunkCatalogPort(Protocol):
    async def add_many(self, chunks: Sequence[Chunk]) -> None:
        """Persist chunk catalog rows (with their ``vector_id`` mapping)."""
        ...

    async def get(self, chunk_id: str) -> Chunk | None:
        ...

    async def list_by_document(self, doc_id: str) -> Sequence[Chunk]:
        """All chunks of a document, ordered by ``ordinal`` (re-ingestion/supersede)."""
        ...

    async def count_by_repository(self, repository: Repository) -> int:
        ...
