"""Tests for the ChromaDB ``VectorStorePort`` adapter against an in-memory fake.

The fake mimics the slice of Chroma the adapter uses (cosine search + ``where``
filtering) so the adapter's real logic is verified without the heavy ``chromadb``
dependency: collection isolation, the engagement-scope pre-filter, the
fail-closed group/classification post-filter, score ordering, ``k`` truncation,
metadata round-trip, and delete/count.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import pytest

from app.domain.chunks.chunk import Chunk, ChunkSpan
from app.domain.documents.acl import AccessControl
from app.domain.ports.vector_store import AclFilter, EmbeddedChunk
from app.domain.repositories.repository import Repository, RoleInGeneration
from app.infrastructure.vector_store.chromadb.adapter import ChromaVectorStore
from app.infrastructure.vector_store.chromadb.client import QueryResult


# --- in-memory fake of the Chroma client seam --------------------------------


def _cosine_distance(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return 1.0 - (dot / (na * nb)) if na and nb else 1.0


def _matches(md: dict[str, Any], where: dict[str, Any] | None) -> bool:
    if not where:
        return True
    for key, cond in where.items():
        if key == "$and":
            if not all(_matches(md, c) for c in cond):
                return False
        elif key == "$or":
            if not any(_matches(md, c) for c in cond):
                return False
        elif isinstance(cond, dict) and "$in" in cond:
            if md.get(key) not in cond["$in"]:
                return False
        else:
            if md.get(key) != cond:
                return False
    return True


class FakeCollection:
    def __init__(self) -> None:
        self._rows: dict[str, dict[str, Any]] = {}

    def upsert(self, *, ids, embeddings, documents, metadatas) -> None:  # type: ignore[no-untyped-def]
        for i, emb, doc, md in zip(ids, embeddings, documents, metadatas, strict=True):
            self._rows[i] = {"embedding": list(emb), "document": doc, "metadata": dict(md)}

    def query(self, *, query_embeddings, n_results, where) -> QueryResult:  # type: ignore[no-untyped-def]
        q = query_embeddings[0]
        scored = [
            (i, r, _cosine_distance(q, r["embedding"]))
            for i, r in self._rows.items()
            if _matches(r["metadata"], where)
        ]
        scored.sort(key=lambda t: t[2])
        scored = scored[:n_results]
        return QueryResult(
            ids=[[i for i, _, _ in scored]],
            documents=[[r["document"] for _, r, _ in scored]],
            metadatas=[[r["metadata"] for _, r, _ in scored]],
            distances=[[d for _, _, d in scored]],
        )

    def delete(self, *, ids) -> None:  # type: ignore[no-untyped-def]
        for i in ids:
            self._rows.pop(i, None)

    def count(self) -> int:
        return len(self._rows)


class FakeChromaClient:
    def __init__(self) -> None:
        self._collections: dict[str, FakeCollection] = {}

    def get_or_create_collection(self, name: str) -> FakeCollection:
        return self._collections.setdefault(name, FakeCollection())


# --- fixtures ----------------------------------------------------------------


def _chunk(
    chunk_id: str,
    *,
    groups: set[str],
    engagement: str | None,
    metadata: dict[str, Any] | None = None,
) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        doc_id=f"doc-{chunk_id}",
        repository=Repository.FINANCIAL,
        role_in_generation=RoleInGeneration.EVIDENCE,
        text=f"text of {chunk_id}",
        ordinal=0,
        span=ChunkSpan(page_start=1, page_end=1, bbox=(0.0, 0.0, 1.0, 1.0)),
        access=AccessControl(
            acl_groups=frozenset(groups),
            engagement_id=engagement,
            classification="confidential",
        ),
        embedding_model_version="local-embed-v1",
        metadata=metadata or {},
    )


@pytest.fixture
def store() -> ChromaVectorStore:
    return ChromaVectorStore(FakeChromaClient(), overfetch=4)


# query is closest to c3, then c4, then c1, then c2
_QUERY = [1.0, 0.0]
_VECTORS = {
    "c1": [0.90, 0.10],
    "c2": [0.50, 0.50],
    "c3": [0.99, 0.01],
    "c4": [0.95, 0.05],
}


async def _seed(store: ChromaVectorStore) -> None:
    items = [
        EmbeddedChunk(
            _chunk("c1", groups={"analysts"}, engagement="eng-7",
                   metadata={"fiscal_year": 2024, "statement_type": "income"}),
            _VECTORS["c1"],
        ),
        EmbeddedChunk(
            _chunk("c2", groups={"analysts"}, engagement=None,
                   metadata={"fiscal_year": 2023, "statement_type": "balance"}),
            _VECTORS["c2"],
        ),
        EmbeddedChunk(  # different engagement → excluded by pre-filter
            _chunk("c3", groups={"analysts"}, engagement="eng-8"),
            _VECTORS["c3"],
        ),
        EmbeddedChunk(  # caller not in group → excluded by post-filter
            _chunk("c4", groups={"partners"}, engagement="eng-7"),
            _VECTORS["c4"],
        ),
    ]
    await store.upsert(Repository.FINANCIAL, items)


_CALLER = AclFilter(caller_groups=frozenset({"analysts"}), caller_engagement_id="eng-7")


async def test_acl_pre_and_post_filter(store: ChromaVectorStore) -> None:
    await _seed(store)
    results = await store.query(Repository.FINANCIAL, _QUERY, k=10, acl=_CALLER)
    ids = [r.chunk.chunk_id for r in results]
    # c3 dropped by engagement pre-filter, c4 dropped by group post-filter.
    assert ids == ["c1", "c2"]
    # Closest permitted (c1) ranks first; scores are similarities (higher = closer).
    assert results[0].score > results[1].score


async def test_k_truncation_after_filtering(store: ChromaVectorStore) -> None:
    await _seed(store)
    results = await store.query(Repository.FINANCIAL, _QUERY, k=1, acl=_CALLER)
    assert [r.chunk.chunk_id for r in results] == ["c1"]


async def test_repository_metadata_filter_uses_clean_field_names(
    store: ChromaVectorStore,
) -> None:
    await _seed(store)
    # Caller filters on the domain field name, not the storage prefix.
    results = await store.query(
        Repository.FINANCIAL, _QUERY, k=10, acl=_CALLER, where={"fiscal_year": 2024}
    )
    assert [r.chunk.chunk_id for r in results] == ["c1"]


async def test_metadata_and_acl_roundtrip(store: ChromaVectorStore) -> None:
    await _seed(store)
    results = await store.query(Repository.FINANCIAL, _QUERY, k=1, acl=_CALLER)
    chunk = results[0].chunk
    assert chunk.role_in_generation is RoleInGeneration.EVIDENCE
    assert chunk.repository is Repository.FINANCIAL
    assert chunk.metadata == {"fiscal_year": 2024, "statement_type": "income"}
    assert chunk.access.engagement_id == "eng-7"
    assert chunk.access.acl_groups == frozenset({"analysts"})
    assert chunk.span.bbox == (0.0, 0.0, 1.0, 1.0)
    assert chunk.vector_id == "c1"


async def test_caller_without_engagement_sees_only_global(store: ChromaVectorStore) -> None:
    await _seed(store)
    anon = AclFilter(caller_groups=frozenset({"analysts"}), caller_engagement_id=None)
    results = await store.query(Repository.FINANCIAL, _QUERY, k=10, acl=anon)
    # Only the global/un-scoped chunk c2 is visible.
    assert [r.chunk.chunk_id for r in results] == ["c2"]


async def test_count_and_delete(store: ChromaVectorStore) -> None:
    await _seed(store)
    assert await store.count(Repository.FINANCIAL) == 4
    await store.delete(Repository.FINANCIAL, ["c1"])
    assert await store.count(Repository.FINANCIAL) == 3
    results = await store.query(Repository.FINANCIAL, _QUERY, k=10, acl=_CALLER)
    assert "c1" not in [r.chunk.chunk_id for r in results]


async def test_collection_isolation(store: ChromaVectorStore) -> None:
    await _seed(store)
    # A different repository is a different collection — no leakage.
    assert await store.count(Repository.PROPOSAL) == 0
    assert await store.query(Repository.PROPOSAL, _QUERY, k=10, acl=_CALLER) == []
