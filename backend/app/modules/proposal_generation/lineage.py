"""Small lineage helpers shared by generation guardrails and the orchestrator.

Keeps the derivation of a human-readable source name (for ``RetrievalHit`` /
``Citation``) in one place so the Execution Report renders consistently.
"""

from __future__ import annotations

from app.domain.chunks.chunk import Chunk


def source_name_of(chunk: Chunk) -> str:
    """A display name for a chunk's source: issuer if known, else the doc id."""
    issuer = chunk.metadata.get("issuer")
    if isinstance(issuer, str) and issuer.strip():
        return issuer.strip()
    return chunk.doc_id
