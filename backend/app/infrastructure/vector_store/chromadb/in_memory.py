"""In-memory ChromaDB client — local-dev implementation of the client seam.

Implements ``ChromaClientPort`` with cosine search and ``where`` matching so the
``ChromaVectorStore`` adapter runs end-to-end locally (``ENVIRONMENT=local``)
without a ChromaDB server. Behavior mirrors the slice of Chroma the adapter uses;
it is not a performance store — it is for local parity and tests.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from app.infrastructure.vector_store.chromadb.client import QueryResult


def _cosine_distance(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
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
        elif isinstance(cond, dict) and "$ne" in cond:
            if md.get(key) == cond["$ne"]:
                return False
        else:
            if md.get(key) != cond:
                return False
    return True


class InMemoryChromaCollection:
    def __init__(self) -> None:
        self._rows: dict[str, dict[str, Any]] = {}

    def upsert(
        self,
        *,
        ids: Sequence[str],
        embeddings: Sequence[Sequence[float]],
        documents: Sequence[str],
        metadatas: Sequence[dict[str, Any]],
    ) -> None:
        for i, emb, doc, md in zip(ids, embeddings, documents, metadatas, strict=True):
            self._rows[i] = {"embedding": list(emb), "document": doc, "metadata": dict(md)}

    def query(
        self,
        *,
        query_embeddings: Sequence[Sequence[float]],
        n_results: int,
        where: dict[str, Any] | None,
    ) -> QueryResult:
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

    def delete(self, *, ids: Sequence[str]) -> None:
        for i in ids:
            self._rows.pop(i, None)

    def count(self) -> int:
        return len(self._rows)


class InMemoryChromaClient:
    def __init__(self) -> None:
        self._collections: dict[str, InMemoryChromaCollection] = {}

    def get_or_create_collection(self, name: str) -> InMemoryChromaCollection:
        return self._collections.setdefault(name, InMemoryChromaCollection())
