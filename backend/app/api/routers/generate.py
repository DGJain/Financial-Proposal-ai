"""Generation endpoint — run the federated RAG pipeline for one brief.

``POST /generate`` adapts HTTP ↔ the ``GenerateProposal`` use-case built by the
composition root. The brief is the JSON body; the caller's ACL/engagement context
(stamped onto retrieval as the deal-team wall) comes from ``X-*`` headers, exactly
as ingestion/curation do. The response is synchronous: a clean run returns the
grounded proposal with its confidence band, contribution metrics, citations, and a
``report_id`` (the gen_id) that opens the Execution Report; a refusal/block returns
the same envelope with no proposal and a reason.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from app.api.schemas.generation import (
    AttachmentExtractResponse,
    GenerateRequest,
    GenerateResponse,
)
from app.container import Container, get_container
from app.domain.documents.enums import FileType
from app.domain.generation.brief import (
    BriefAttachment,
    GenerationBrief,
    RequesterContext,
)
from app.domain.ingestion.extracted import ExtractedDocument
from app.modules.proposal_generation.graph.orchestrator import GenerateProposalCommand

router = APIRouter(prefix="/generate", tags=["generation"])

ContainerDep = Annotated[Container, Depends(get_container)]


def _parse_groups(raw: str | None) -> frozenset[str]:
    if not raw:
        return frozenset()
    return frozenset(g.strip() for g in raw.split(",") if g.strip())


@router.post("", response_model=GenerateResponse)
async def generate(
    body: GenerateRequest,
    container: ContainerDep,
    x_acl_groups: Annotated[str | None, Header()] = None,
    x_engagement_id: Annotated[str | None, Header()] = None,
    x_classification: Annotated[str | None, Header()] = None,
    x_requested_by: Annotated[str | None, Header()] = None,
) -> GenerateResponse:
    # Query-first intake: infer the company / period / sector / figures from the
    # free-text query for any field the caller left blank. Explicit Advanced-panel
    # values always win; a guess still passes the retrieval metadata gate, so it can
    # only fail to ground — never fabricate evidence.
    entity, fiscal_year = body.entity, body.fiscal_year
    sector, line_items = body.sector, list(body.line_items)
    needs_inference = body.query.strip() and (
        not (entity or "").strip()
        or fiscal_year is None
        or not (sector or "").strip()
        or not line_items
    )
    if needs_inference:
        inferred = await container.brief_extractor().infer(body.query)
        entity = (entity or "").strip() or inferred.entity
        fiscal_year = fiscal_year if fiscal_year is not None else inferred.fiscal_year
        sector = (sector or "").strip() or inferred.sector
        line_items = line_items or list(inferred.line_items)

    command = GenerateProposalCommand(
        brief=GenerationBrief(
            title=body.title,
            proposal_type=body.proposal_type,
            entity=entity or None,
            fiscal_year=fiscal_year,
            sector=sector or None,
            line_items=tuple(line_items),
            instructions=body.framing_instructions(),
            attachments=tuple(
                BriefAttachment(name=att.name, text=att.text)
                for att in body.attachments
                if att.text.strip()
            ),
        ),
        requester=RequesterContext(
            engagement_id=x_engagement_id,
            caller_groups=_parse_groups(x_acl_groups),
            classification=x_classification,
            requested_by=x_requested_by or "system",
        ),
    )
    result = await container.generate_proposal().execute(command)
    return GenerateResponse.from_domain(result.event, result.proposal)


@router.post("/extract", response_model=AttachmentExtractResponse)
async def extract_attachment(
    request: Request,
    container: ContainerDep,
    filename: str,
    file_type: FileType,
) -> AttachmentExtractResponse:
    """Extract plain text from an uploaded binary so it can ride along as context.

    The composer posts the file's raw bytes (no multipart dependency — same shape
    as ``/ingest/financial``); the response is the document's text, flattened from
    the shared extraction model. Formats whose library/binary isn't available here
    (e.g. image OCR) return ``extracted=false`` with a reason rather than erroring,
    so the UI can fall back to attaching the file by name. This text is *context*
    for the prose only — it never becomes citable evidence."""
    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file body.")
    try:
        document = await container.extractor.extract(data, file_type=file_type)
    except Exception as exc:  # noqa: BLE001 — missing optional lib / unreadable file
        return AttachmentExtractResponse(
            name=filename,
            extracted=False,
            detail=f"Could not extract text ({type(exc).__name__}); attached by name only.",
        )
    text = _flatten_document(document)
    if not text:
        return AttachmentExtractResponse(
            name=filename,
            extracted=False,
            detail="No machine-readable text found (likely a scanned image).",
        )
    return AttachmentExtractResponse(
        name=filename, text=text, extracted=True, char_count=len(text)
    )


def _flatten_document(document: ExtractedDocument) -> str:
    """Flatten the layout model to plain text: page prose followed by table rows."""
    parts: list[str] = []
    if document.full_text:
        parts.append(document.full_text)
    parts.extend(table.render() for _page, table in document.tables())
    return "\n\n".join(p for p in parts if p.strip())
