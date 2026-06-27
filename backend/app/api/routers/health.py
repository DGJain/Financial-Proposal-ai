"""Health & readiness endpoints.

``/health`` is a lightweight **liveness** probe that also surfaces the active
wiring (environment, air-gap flag, model provider) — useful confirmation that a
fresh deployment booted with the intended providers. It touches only the
lazily-built gateway/embedder (no DB / no network in local).

``/ready`` is the K8s **readiness** probe: it round-trips the backing stores
(PostgreSQL catalog + ChromaDB vector store) and returns ``503`` until every
dependency answers, so traffic is only routed to a pod once it can actually serve.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.container import Container, get_container

router = APIRouter(tags=["health"])

ContainerDep = Annotated[Container, Depends(get_container)]


@router.get("/health")
async def health(container: ContainerDep) -> dict[str, object]:
    settings = container.settings
    return {
        "status": "ok",
        "service": settings.api_title,
        "version": settings.api_version,
        "environment": settings.environment.value,
        "air_gapped": settings.air_gapped,
        "model_provider": settings.ai.provider.value,
        "llm_model_id": container.llm_gateway.model_id,
        "embedding_model_version": container.embedder.model_version,
    }


_DEPENDENCY_CHECKS = {
    "database": Container.ping_database,
    "vector_store": Container.ping_vector_store,
}


@router.get("/ready")
async def ready(container: ContainerDep) -> dict[str, object]:
    checks: dict[str, bool] = {}
    for name, probe in _DEPENDENCY_CHECKS.items():
        try:
            await probe(container)
            checks[name] = True
        except Exception:  # noqa: BLE001 — any failure means "not ready"
            checks[name] = False
    if not all(checks.values()):
        raise HTTPException(status_code=503, detail={"ready": False, "checks": checks})
    return {"ready": True, "checks": checks}
