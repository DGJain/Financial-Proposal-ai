"""Deterministic hashing embedder — local-dev / test implementation of ``EmbedderPort``.

A dependency-free hashing vectorizer: each token is hashed into a fixed-dimension
bag-of-hashes vector, then L2-normalized. It carries no real semantics, but it is
**deterministic** and gives similar texts similar vectors — enough to exercise the
full ingest → embed → store → retrieve path locally without a GPU embedding
server. Selected by the composition root when ``ENVIRONMENT=local``.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence

_TOKEN = re.compile(r"\w+")


class DeterministicEmbedder:
    def __init__(self, dim: int = 256, model_version: str = "deterministic-hash-v1") -> None:
        self._dim = dim
        self._model_version = model_version

    @property
    def model_version(self) -> str:
        return self._model_version

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self._dim
        for token in _TOKEN.findall(text.lower()):
            digest = hashlib.sha1(token.encode("utf-8")).digest()  # noqa: S324 (non-crypto use)
            index = int.from_bytes(digest[:4], "big") % self._dim
            sign = 1.0 if digest[4] & 1 else -1.0
            vec[index] += sign
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0.0:
            vec[0] = 1.0
            return vec
        return [v / norm for v in vec]

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._embed_one(text)
