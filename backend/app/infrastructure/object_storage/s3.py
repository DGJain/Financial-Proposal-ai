"""S3-compatible object store (MinIO in-cluster) implementing ``ObjectStorePort``.

Stores raw originals (immutable) and versioned copies in two buckets. ``boto3`` is
imported lazily so importing this module never requires the dependency; the
endpoint is always an internal address (air-gapped). Sync boto3 calls are wrapped
in ``asyncio.to_thread``.
"""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlparse

from app.core.config import ObjectStorageSettings


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    parsed = urlparse(uri)
    if parsed.scheme != "s3":
        raise ValueError(f"not an s3 uri: {uri!r}")
    return parsed.netloc, parsed.path.lstrip("/")


class S3ObjectStore:
    def __init__(self, settings: ObjectStorageSettings) -> None:
        self._settings = settings
        self._client: Any | None = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            import boto3  # lazy: keeps the dependency optional at import time

            self._client = boto3.client(
                "s3",
                endpoint_url=self._settings.endpoint_url,
                aws_access_key_id=self._settings.access_key,
                aws_secret_access_key=self._settings.secret_key,
                region_name=self._settings.region,
            )
        return self._client

    async def put_raw(self, key: str, data: bytes, *, content_type: str) -> str:
        return await self._put(self._settings.bucket_raw, key, data, content_type)

    async def put_versioned(self, key: str, data: bytes, *, content_type: str) -> str:
        return await self._put(self._settings.bucket_versioned, key, data, content_type)

    async def _put(self, bucket: str, key: str, data: bytes, content_type: str) -> str:
        client = self._ensure_client()
        await asyncio.to_thread(
            client.put_object, Bucket=bucket, Key=key, Body=data, ContentType=content_type
        )
        return f"s3://{bucket}/{key}"

    async def get(self, uri: str) -> bytes:
        bucket, key = _parse_s3_uri(uri)
        client = self._ensure_client()
        response = await asyncio.to_thread(client.get_object, Bucket=bucket, Key=key)
        return await asyncio.to_thread(response["Body"].read)

    async def exists(self, uri: str) -> bool:
        bucket, key = _parse_s3_uri(uri)
        client = self._ensure_client()
        try:
            await asyncio.to_thread(client.head_object, Bucket=bucket, Key=key)
        except Exception:  # noqa: BLE001 — boto3 ClientError (404) means "absent"
            return False
        return True
