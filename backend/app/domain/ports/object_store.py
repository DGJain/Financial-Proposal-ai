"""Object-store port — raw + versioned source originals.

Backed by in-cluster S3-compatible storage (MinIO). Raw originals are immutable;
versioned copies support the slower, versioned change cadence of curated
proposals and templates (ARCHITECTURE_SUMMARY.md "Deployment Overview").
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ObjectStorePort(Protocol):
    async def put_raw(self, key: str, data: bytes, *, content_type: str) -> str:
        """Store an immutable raw original; returns its object URI."""
        ...

    async def put_versioned(self, key: str, data: bytes, *, content_type: str) -> str:
        """Store a versioned copy; returns the version-qualified object URI."""
        ...

    async def get(self, uri: str) -> bytes:
        """Fetch object bytes by URI."""
        ...

    async def exists(self, uri: str) -> bool:
        ...
