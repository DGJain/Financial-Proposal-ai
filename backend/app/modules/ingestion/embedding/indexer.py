"""Embed + index stage — chunks → vectors → ChromaDB ``repo_financial``.

The last data-plane stage of ingestion: embed every chunk's text with the local
``EmbedderPort`` and upsert the resulting vectors into the financial collection
via ``VectorStorePort``. The ACL stamped on each chunk is encoded into the vector
metadata by the adapter, so retrieval pre-filtering works without any join.

``vector_id`` is set to the ``chunk_id`` (a stable, content-addressable id) so
re-ingestion of the same document supersedes rather than duplicates, and the
catalog row's ``vector_id`` column points straight at the stored vector.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from app.domain.chunks.chunk import Chunk
from app.domain.ports.embedder import EmbedderPort
from app.domain.ports.vector_store import EmbeddedChunk, VectorStorePort
from app.domain.repositories.repository import Repository


@dataclass(frozen=True, slots=True)
class EmbedAndIndex:
    """Embeds chunks and upserts them into a repository's vector collection."""

    embedder: EmbedderPort
    vector_store: VectorStorePort

    async def run(self, repository: Repository, chunks: list[Chunk]) -> list[Chunk]:
        """Embed + upsert into ``repository``'s collection; returns the chunks
        with ``vector_id`` populated."""
        if not chunks:
            return []
        embeddings = await self.embedder.embed_documents([c.text for c in chunks])
        indexed = [replace(chunk, vector_id=chunk.chunk_id) for chunk in chunks]
        items = [
            EmbeddedChunk(chunk=chunk, embedding=embedding)
            for chunk, embedding in zip(indexed, embeddings, strict=True)
        ]
        await self.vector_store.upsert(repository, items)
        return indexed
