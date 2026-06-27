"""HTTP embedder — calls the in-cluster embedding server (``ObjectStorePort`` sibling).

Implements ``EmbedderPort`` against the air-gapped embedding service in the ``ai``
namespace. ``httpx`` is imported lazily. ``model_version`` is pinned from settings
and stamped onto every chunk so a collection's vectors stay comparable.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.core.config import AISettings


class HttpEmbedder:
    def __init__(self, settings: AISettings) -> None:
        self._endpoint = settings.embedding_endpoint.rstrip("/")
        self._model_version = settings.embedding_model_version
        self._timeout = settings.request_timeout_seconds
        self._client: Any | None = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            import httpx  # lazy

            self._client = httpx.AsyncClient(base_url=self._endpoint, timeout=self._timeout)
        return self._client

    @property
    def model_version(self) -> str:
        return self._model_version

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        client = self._ensure_client()
        response = await client.post("/embed", json={"inputs": list(texts)})
        response.raise_for_status()
        return list(response.json()["embeddings"])

    async def embed_query(self, text: str) -> list[float]:
        embeddings = await self.embed_documents([text])
        return embeddings[0]

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
