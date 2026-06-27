"""Low-level ChromaDB client seam.

The adapter depends on these narrow Protocols, not on the ``chromadb`` package
directly. That keeps the adapter's logic unit-testable with an in-memory fake and
lets the real client be a thin, lazily-imported wrapper — important for an
air-gapped build where ChromaDB runs as an in-cluster server (HttpClient), never
embedded.

The Chroma client API is synchronous; the adapter wraps these calls in
``asyncio.to_thread`` so it never blocks the event loop.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class QueryResult:
    """Mirror of chromadb's query return shape (one inner list per query)."""

    ids: list[list[str]]
    documents: list[list[str]]
    metadatas: list[list[dict[str, Any]]]
    distances: list[list[float]]


class ChromaCollectionPort(Protocol):
    """The subset of a Chroma collection the adapter uses."""

    def upsert(
        self,
        *,
        ids: Sequence[str],
        embeddings: Sequence[Sequence[float]],
        documents: Sequence[str],
        metadatas: Sequence[dict[str, Any]],
    ) -> None: ...

    def query(
        self,
        *,
        query_embeddings: Sequence[Sequence[float]],
        n_results: int,
        where: dict[str, Any] | None,
    ) -> QueryResult: ...

    def delete(self, *, ids: Sequence[str]) -> None: ...

    def count(self) -> int: ...


class ChromaClientPort(Protocol):
    def get_or_create_collection(self, name: str) -> ChromaCollectionPort: ...


def make_chroma_client() -> ChromaClientPort:
    """Build the real in-cluster ChromaDB HTTP client from settings.

    ``chromadb`` is imported lazily so importing this module (and the adapter)
    never requires the heavy dependency — only constructing the live client does.
    """
    import chromadb  # local import: keeps the package optional at import time

    from app.core.config import get_settings

    settings = get_settings()
    return chromadb.HttpClient(  # type: ignore[return-value]
        host=settings.chroma.host,
        port=settings.chroma.port,
    )
