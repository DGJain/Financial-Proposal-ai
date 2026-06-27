"""In-memory object store — local-dev / test implementation of ``ObjectStorePort``.

Selected by the composition root when ``ENVIRONMENT=local`` so the platform runs
without a MinIO server. Mirrors the ``s3://bucket/key`` URI scheme of the real
adapter so swapping them changes nothing for callers.
"""

from __future__ import annotations


class InMemoryObjectStore:
    def __init__(self, bucket_raw: str = "raw-originals", bucket_versioned: str = "versioned-originals") -> None:
        self._bucket_raw = bucket_raw
        self._bucket_versioned = bucket_versioned
        self._store: dict[str, bytes] = {}

    async def put_raw(self, key: str, data: bytes, *, content_type: str) -> str:
        uri = f"s3://{self._bucket_raw}/{key}"
        self._store[uri] = data
        return uri

    async def put_versioned(self, key: str, data: bytes, *, content_type: str) -> str:
        uri = f"s3://{self._bucket_versioned}/{key}"
        self._store[uri] = data
        return uri

    async def get(self, uri: str) -> bytes:
        try:
            return self._store[uri]
        except KeyError as exc:
            raise FileNotFoundError(uri) from exc

    async def exists(self, uri: str) -> bool:
        return uri in self._store
