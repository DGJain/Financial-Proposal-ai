"""Ingestion endpoints — trigger the financial ingestion pipeline.

Phase 1 exposes one route: upload a financial source and run it through
``extract → redact → classify → gate → chunk → embed → index``. The raw bytes are
sent as the request body (no multipart dependency); the caller's ACL context —
which is stamped onto every resulting chunk — comes from headers so the deal-team
wall is enforced from the moment of ingestion.

The heavy work is delegated to the ``IngestFinancialDocument`` use-case built by
the composition root; this layer only adapts HTTP ↔ the use-case.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from app.container import Container, get_container
from app.domain.documents.enums import FileType
from app.modules.ingestion.pipeline.ingest_financial import (
    CallerContext,
    IngestionRequest,
)

router = APIRouter(prefix="/ingest", tags=["ingestion"])

ContainerDep = Annotated[Container, Depends(get_container)]


def _parse_groups(raw: str | None) -> frozenset[str]:
    if not raw:
        return frozenset()
    return frozenset(g.strip() for g in raw.split(",") if g.strip())


@router.post("/financial")
async def ingest_financial(
    request: Request,
    container: ContainerDep,
    filename: str,
    file_type: FileType,
    x_acl_groups: Annotated[str | None, Header()] = None,
    x_engagement_id: Annotated[str | None, Header()] = None,
    x_classification: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="Empty upload body.")

    use_case = container.ingest_financial()
    result = await use_case.execute(
        IngestionRequest(
            data=data,
            filename=filename,
            file_type=file_type,
            caller=CallerContext(
                acl_groups=_parse_groups(x_acl_groups),
                engagement_id=x_engagement_id,
                classification=x_classification,
            ),
        )
    )
    payload: dict[str, object] = {
        "status": result.status.value,
        "doc_id": result.doc_id,
        "repository": result.repository.value,
        "chunk_count": result.chunk_count,
    }
    if result.gate_verdict is not None:
        payload["gate_verdict"] = result.gate_verdict.value
    if result.review_reason is not None:
        payload["review_reason"] = result.review_reason.value
    if result.quality is not None:
        payload["quality"] = {
            "eqs": result.quality.eqs,
            "cfr": result.quality.cfr,
            "rpr": result.quality.rpr,
            "ocr_confidence": result.quality.ocr_confidence,
        }
    return payload
