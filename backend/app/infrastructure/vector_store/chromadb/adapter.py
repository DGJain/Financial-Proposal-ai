"""``ChromaVectorStore`` — the ChromaDB adapter implementing ``VectorStorePort``.

Each repository is one named, isolated collection (cross-repository leakage is
impossible because a query targets exactly one collection). ACL is enforced in
two layers:

1. **Pre-filter** pushed into Chroma's ``where`` on ``engagement_id`` — the
   deal-team wall, efficient and done in the store.
2. **Fail-closed post-filter** via ``AccessControl.permits`` on the reconstructed
   chunk — enforces group membership and classification that scalar metadata
   can't express as a list pre-filter, and guarantees nothing slips through.

Because the post-filter can drop candidates, the store over-fetches and then
truncates to the requested ``k``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

from app.domain.ports.vector_store import (
    AclFilter,
    EmbeddedChunk,
    ScoredChunk,
    permits,
)
from app.domain.repositories.repository import Repository, collection_name
from app.infrastructure.vector_store.chromadb.client import ChromaClientPort
from app.infrastructure.vector_store.chromadb.metadata import (
    GLOBAL_ENGAGEMENT,
    REPO_PREFIX,
    RESERVED_FIELDS,
    from_result,
    to_metadata,
)


class ChromaVectorStore:
    """Adapter over the three ACL-tagged ChromaDB collections."""

    def __init__(self, client: ChromaClientPort, *, overfetch: int = 4) -> None:
        self._client = client
        self._overfetch = max(1, overfetch)

    def _collection(self, repository: Repository) -> Any:
        return self._client.get_or_create_collection(collection_name(repository))

    async def upsert(self, repository: Repository, items: Sequence[EmbeddedChunk]) -> None:
        if not items:
            return
        collection = self._collection(repository)
        await asyncio.to_thread(
            collection.upsert,
            ids=[item.chunk.chunk_id for item in items],
            embeddings=[list(item.embedding) for item in items],
            documents=[item.chunk.text for item in items],
            metadatas=[to_metadata(item.chunk) for item in items],
        )

    async def query(
        self,
        repository: Repository,
        embedding: Sequence[float],
        *,
        k: int,
        acl: AclFilter,
        where: dict[str, Any] | None = None,
    ) -> list[ScoredChunk]:
        if k <= 0:
            return []
        collection = self._collection(repository)
        final_where = _merge_where(_acl_where(acl), _translate_user_where(where))
        result = await asyncio.to_thread(
            collection.query,
            query_embeddings=[list(embedding)],
            n_results=k * self._overfetch,
            where=final_where,
        )

        ids = result.ids[0] if result.ids else []
        documents = result.documents[0] if result.documents else []
        metadatas = result.metadatas[0] if result.metadatas else []
        distances = result.distances[0] if result.distances else []

        scored: list[ScoredChunk] = []
        for chunk_id, document, md, distance in zip(
            ids, documents, metadatas, distances, strict=False
        ):
            chunk = from_result(chunk_id, document, md)
            if not permits(chunk.access, acl):  # fail-closed defense in depth
                continue
            scored.append(ScoredChunk(chunk=chunk, score=_to_score(distance)))
            if len(scored) >= k:
                break
        return scored

    async def delete(self, repository: Repository, chunk_ids: Sequence[str]) -> None:
        if not chunk_ids:
            return
        collection = self._collection(repository)
        await asyncio.to_thread(collection.delete, ids=list(chunk_ids))

    async def count(self, repository: Repository) -> int:
        collection = self._collection(repository)
        return int(await asyncio.to_thread(collection.count))


def _acl_where(acl: AclFilter) -> dict[str, Any]:
    """Engagement-scope pre-filter: caller's engagement OR global/un-scoped."""
    if acl.caller_engagement_id is not None:
        return {"engagement_id": {"$in": [acl.caller_engagement_id, GLOBAL_ENGAGEMENT]}}
    return {"engagement_id": GLOBAL_ENGAGEMENT}


def _merge_where(
    acl_where: dict[str, Any], user_where: dict[str, Any] | None
) -> dict[str, Any]:
    if not user_where:
        return acl_where
    return {"$and": [acl_where, user_where]}


def _translate_user_where(where: dict[str, Any] | None) -> dict[str, Any] | None:
    """Map caller field names to stored metadata keys.

    Repository-specific fields are stored ``x_``-prefixed (see metadata codec), so
    a caller filter like ``{"fiscal_year": 2024}`` becomes ``{"x_fiscal_year":
    2024}``. Logical operators (``$and``/``$or``) recurse; reserved base fields and
    comparison operators pass through untouched. This keeps the port contract
    clean — callers never see the storage prefix.
    """
    if not where:
        return where
    translated: dict[str, Any] = {}
    for key, value in where.items():
        if key.startswith("$"):
            if isinstance(value, list):
                translated[key] = [_translate_user_where(clause) for clause in value]
            else:
                translated[key] = value
        elif key in RESERVED_FIELDS:
            translated[key] = value
        else:
            translated[f"{REPO_PREFIX}{key}"] = value
    return translated


def _to_score(distance: float) -> float:
    """Convert Chroma cosine distance to a similarity score (higher = better)."""
    return 1.0 - distance
