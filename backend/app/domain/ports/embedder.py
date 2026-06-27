"""Embedder port — the local embedding model behind a stable interface.

The model is local (air-gapped). ``model_version`` is first-class so every chunk
records which model produced its vector; a collection's vectors are only ever
compared within one embedding-model version.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbedderPort(Protocol):
    @property
    def model_version(self) -> str:
        """Identifier pinned onto every embedded chunk for comparability."""
        ...

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a batch of chunk texts for indexing."""
        ...

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query string for retrieval."""
        ...
