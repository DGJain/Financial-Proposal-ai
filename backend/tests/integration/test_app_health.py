"""Boot test — the FastAPI app starts from the composition root and serves /health.

Sets the minimal local environment before importing the app so settings validate
(PostgreSQL/Redis DSNs are required even in local; object-storage secrets are
not). Confirms the local wiring resolves to the in-process providers.
"""

from __future__ import annotations

import os

os.environ.setdefault("ENVIRONMENT", "local")
os.environ.setdefault("AIR_GAPPED", "true")
os.environ.setdefault("POSTGRES_DSN", "postgresql+asyncpg://u:p@localhost:5432/fpp")
os.environ.setdefault("REDIS_DSN", "redis://localhost:6379/0")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402


def test_health_reports_local_wiring() -> None:
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["environment"] == "local"
    assert body["air_gapped"] is True
    assert body["llm_model_id"] == "echo-local"  # local → echo gateway
    assert body["embedding_model_version"]  # deterministic embedder wired
