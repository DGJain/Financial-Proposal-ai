"""Codec between a domain ``Chunk`` and Chroma's scalar-only metadata.

Chroma metadata values must be scalars (str/int/float/bool) — no lists. So ACL
groups are encoded into a single delimited string, the engagement scope uses a
sentinel for "global" (un-scoped) content, and repository-specific metadata is
flattened under an ``x_`` prefix so it stays filterable without colliding with
reserved keys.

The encoded ``engagement_id`` is what the adapter pre-filters on (the deal-team
wall); the encoded groups/classification let the adapter reconstruct the chunk's
``AccessControl`` for a fail-closed post-filter.
"""

from __future__ import annotations

from typing import Any

from app.domain.chunks.chunk import Chunk, ChunkSpan
from app.domain.documents.acl import AccessControl
from app.domain.repositories.repository import Repository, RoleInGeneration

GLOBAL_ENGAGEMENT = "__global__"
_GROUP_DELIM = "|"
REPO_PREFIX = "x_"
RESERVED_FIELDS = {
    "doc_id",
    "repository",
    "role_in_generation",
    "ordinal",
    "page_start",
    "page_end",
    "embedding_model_version",
    "engagement_id",
    "classification",
    "acl_groups",
    "bbox",
}


def encode_groups(groups: frozenset[str]) -> str:
    """``{a, b}`` -> ``"|a|b|"`` so a substring match is exact and unambiguous."""
    if not groups:
        return ""
    return _GROUP_DELIM + _GROUP_DELIM.join(sorted(groups)) + _GROUP_DELIM


def decode_groups(encoded: str) -> frozenset[str]:
    return frozenset(p for p in encoded.split(_GROUP_DELIM) if p)


def to_metadata(chunk: Chunk) -> dict[str, Any]:
    md: dict[str, Any] = {
        "doc_id": chunk.doc_id,
        "repository": chunk.repository.value,
        "role_in_generation": chunk.role_in_generation.value,
        "ordinal": chunk.ordinal,
        "page_start": chunk.span.page_start,
        "page_end": chunk.span.page_end,
        "embedding_model_version": chunk.embedding_model_version,
        "engagement_id": chunk.access.engagement_id or GLOBAL_ENGAGEMENT,
        "classification": chunk.access.classification or "",
        "acl_groups": encode_groups(chunk.access.acl_groups),
    }
    if chunk.span.bbox is not None:
        md["bbox"] = ",".join(str(c) for c in chunk.span.bbox)
    for key, value in chunk.metadata.items():
        if isinstance(value, (str, int, float, bool)):
            md[f"{REPO_PREFIX}{key}"] = value
    return md


def _decode_bbox(raw: str | None) -> tuple[float, float, float, float] | None:
    if not raw:
        return None
    parts = tuple(float(p) for p in raw.split(","))
    return parts if len(parts) == 4 else None  # type: ignore[return-value]


def from_result(chunk_id: str, document_text: str, md: dict[str, Any]) -> Chunk:
    """Reconstruct a domain ``Chunk`` from a Chroma hit (id + document + metadata)."""
    engagement = md.get("engagement_id", GLOBAL_ENGAGEMENT)
    classification = md.get("classification") or None
    access = AccessControl(
        acl_groups=decode_groups(md.get("acl_groups", "")),
        engagement_id=None if engagement == GLOBAL_ENGAGEMENT else engagement,
        classification=classification,
    )
    repo_metadata = {
        key[len(REPO_PREFIX) :]: value
        for key, value in md.items()
        if key.startswith(REPO_PREFIX) and key not in RESERVED_FIELDS
    }
    return Chunk(
        chunk_id=chunk_id,
        doc_id=md["doc_id"],
        repository=Repository(md["repository"]),
        role_in_generation=RoleInGeneration(md["role_in_generation"]),
        text=document_text,
        ordinal=int(md["ordinal"]),
        span=ChunkSpan(
            page_start=int(md["page_start"]),
            page_end=int(md["page_end"]),
            bbox=_decode_bbox(md.get("bbox")),
        ),
        access=access,
        embedding_model_version=md["embedding_model_version"],
        vector_id=chunk_id,
        metadata=repo_metadata,
    )
