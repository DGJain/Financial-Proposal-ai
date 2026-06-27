"""Curation endpoints — the approval gate for the curated repositories.

``POST /curate/{repository}`` ingests a curated proposal or template into its
approval-gated collection. For proposals, the engine runs anonymization
verification: any residual engagement-specific content (figures, PII/MNPI, or a
supplied client identifier) routes the document to review instead of indexing it.
Financial content is rejected here (use the open-upload ``/ingest`` route).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from app.container import Container, get_container
from app.domain.documents.enums import FileType
from app.domain.repositories.repository import Repository
from app.modules.ingestion.pipeline.engine import CallerContext, IngestionRequest

router = APIRouter(prefix="/curate", tags=["curation"])

ContainerDep = Annotated[Container, Depends(get_container)]


def _parse_csv(raw: str | None) -> frozenset[str]:
    if not raw:
        return frozenset()
    return frozenset(item.strip() for item in raw.split(",") if item.strip())


@router.post("/{repository}")
async def curate(
    repository: Repository,
    request: Request,
    container: ContainerDep,
    filename: str,
    file_type: FileType,
    outcome: str | None = None,
    client: str | None = None,
    industry: str | None = None,
    x_acl_groups: Annotated[str | None, Header()] = None,
    x_engagement_id: Annotated[str | None, Header()] = None,
    x_classification: Annotated[str | None, Header()] = None,
    x_known_identifiers: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="Empty upload body.")

    hints: dict[str, str] = {}
    if outcome:
        hints["outcome"] = outcome
    if client:
        hints["client"] = client
    if industry:
        hints["industry"] = industry

    ingestion_request = IngestionRequest(
        data=data,
        filename=filename,
        file_type=file_type,
        caller=CallerContext(
            acl_groups=_parse_csv(x_acl_groups),
            engagement_id=x_engagement_id,
            classification=x_classification,
        ),
        metadata_hints=hints,
        known_identifiers=_parse_csv(x_known_identifiers),
    )

    try:
        result = await container.curate_exemplar().execute(ingestion_request, target=repository)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

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
    return payload
