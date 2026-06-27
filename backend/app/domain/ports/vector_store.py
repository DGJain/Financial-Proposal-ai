"""Vector-store port — the abstraction over ChromaDB's three collections.

Use-cases depend on this Protocol, never on ChromaDB directly (Clean
Architecture DIP). Every query targets exactly one named collection and carries
an ACL pre-filter, so cross-repository leakage is impossible at the boundary
(architecture.md §6 "collection isolation").
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from app.domain.chunks.chunk import Chunk
from app.domain.documents.acl import AccessControl
from app.domain.repositories.repository import Repository


@dataclass(frozen=True, slots=True)
class EmbeddedChunk:
    """A chunk paired with its embedding vector, ready to upsert."""

    chunk: Chunk
    embedding: Sequence[float]


@dataclass(frozen=True, slots=True)
class ScoredChunk:
    """A retrieval candidate: the chunk plus its similarity/relevance score."""

    chunk: Chunk
    score: float


@dataclass(frozen=True, slots=True)
class AclFilter:
    """ACL pre-filter applied to a query, derived from the caller's grants."""

    caller_groups: frozenset[str]
    caller_engagement_id: str | None


@runtime_checkable
class VectorStorePort(Protocol):
    """Abstraction over a namespaced, ACL-tagged vector collection."""

    async def upsert(
        self,
        repository: Repository,
        items: Sequence[EmbeddedChunk],
    ) -> None:
        """Insert/replace embedded chunks in the repository's collection."""
        ...

    async def query(
        self,
        repository: Repository,
        embedding: Sequence[float],
        *,
        k: int,
        acl: AclFilter,
        where: dict[str, Any] | None = None,
    ) -> list[ScoredChunk]:
        """ACL-pre-filtered top-k search within one collection.

        ``where`` carries repository-specific metadata filters (e.g.
        ``fiscal_year``, ``outcome=won``, ``status=approved``).
        """
        ...

    async def delete(self, repository: Repository, chunk_ids: Sequence[str]) -> None:
        """Remove chunks (e.g. on document re-ingestion / supersede)."""
        ...

    async def count(self, repository: Repository) -> int:
        """Number of embedded chunks in a collection (for metrics cards)."""
        ...


def acl_filter_for(access_holder_groups: frozenset[str], engagement_id: str | None) -> AclFilter:
    """Helper to build an :class:`AclFilter` from caller context."""
    return AclFilter(caller_groups=access_holder_groups, caller_engagement_id=engagement_id)


def permits(chunk_access: AccessControl, acl: AclFilter) -> bool:
    """Whether a chunk's ACL admits the caller — fail-closed."""
    return chunk_access.permits(
        caller_groups=acl.caller_groups,
        caller_engagement_id=acl.caller_engagement_id,
    )
