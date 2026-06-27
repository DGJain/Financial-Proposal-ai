"""FastAPI application factory.

Thin delivery layer: it builds the app, wires routers, and manages startup/shutdown.
All dependency construction lives in the composition root (``app.container``); this
module only assembles the HTTP surface. Phase-1+ routers (upload, ingestion,
generation, metrics, history, report) are registered here as they land.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routers import (
    curation,
    generate,
    health,
    history,
    ingestion,
    metrics,
    proposals,
    report,
)
from app.container import get_container
from app.core.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Eagerly resolve the container so misconfiguration fails fast at startup.
    get_container()
    yield
    # Shutdown hooks (engine dispose, httpx client close) are added with the
    # adapters that own those resources.


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.api_title,
        version=settings.api_version,
        lifespan=lifespan,
    )
    app.include_router(health.router)
    app.include_router(ingestion.router)
    app.include_router(curation.router)
    app.include_router(generate.router)
    app.include_router(proposals.router)
    app.include_router(report.router)
    app.include_router(history.router)
    app.include_router(metrics.router)
    return app


app = create_app()
