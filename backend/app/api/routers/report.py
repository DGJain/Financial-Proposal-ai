"""Execution Report endpoint — the forensic drill-in for one run (§6.6).

``GET /report/{gen_id}`` reconstructs exactly what the pipeline retrieved and
produced for one prompt from the append-only audit log + the joined ingestion
quality. Read-only; a refused run still resolves (prompt, zero documents, refusal
reason, no stages). 404 when the gen_id is unknown.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.schemas.analytics import ExecutionReportDTO
from app.container import Container, get_container

router = APIRouter(prefix="/report", tags=["analytics"])

ContainerDep = Annotated[Container, Depends(get_container)]


@router.get("/{gen_id}", response_model=ExecutionReportDTO)
async def get_report(gen_id: str, container: ContainerDep) -> ExecutionReportDTO:
    data = await container.execution_report().execute(gen_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"report {gen_id!r} not found")
    return ExecutionReportDTO.from_domain(data)
