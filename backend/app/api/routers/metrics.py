"""Metrics endpoints — repository composition + generation health (Page 4).

``GET /metrics/repository`` returns the five dashboard repo cards plus the corpus
contribution triple (live counts/freshness of the knowledge base). ``GET
/metrics/generation-health`` returns the rolling-window health aggregates: stat
cards, the per-day run bars, and the information-loss distribution.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.schemas.analytics import GenerationHealthDTO, RepositoryMetricsDTO
from app.container import Container, get_container

router = APIRouter(prefix="/metrics", tags=["analytics"])

ContainerDep = Annotated[Container, Depends(get_container)]


@router.get("/repository", response_model=RepositoryMetricsDTO)
async def repository_metrics(container: ContainerDep) -> RepositoryMetricsDTO:
    data = await container.repository_metrics().execute()
    return RepositoryMetricsDTO.from_domain(data)


@router.get("/generation-health", response_model=GenerationHealthDTO)
async def generation_health(
    container: ContainerDep,
    days: Annotated[int, Query(ge=1, le=90)] = 7,
) -> GenerationHealthDTO:
    data = await container.generation_health().execute(days=days)
    return GenerationHealthDTO.from_domain(data)
