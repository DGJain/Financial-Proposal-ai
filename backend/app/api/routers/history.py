"""Prompt-history endpoint — analytics rows over past runs (ui-design.md Page 5).

``GET /history`` returns a page of nine-field analytics rows (newest first); each
row carries a ``gen_id`` that opens the Execution Report. Backs both the Prompt
History page and the dashboard's Prompt-History Analytics table.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.schemas.analytics import AnalyticsRowDTO, PromptHistoryDTO
from app.container import Container, get_container

router = APIRouter(prefix="/history", tags=["analytics"])

ContainerDep = Annotated[Container, Depends(get_container)]


@router.get("", response_model=PromptHistoryDTO)
async def list_history(
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PromptHistoryDTO:
    rows = await container.prompt_history().execute(limit=limit, offset=offset)
    return PromptHistoryDTO(
        rows=[AnalyticsRowDTO.from_domain(row) for row in rows],
        limit=limit,
        offset=offset,
    )
