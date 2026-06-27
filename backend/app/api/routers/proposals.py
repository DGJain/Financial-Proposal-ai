"""Proposal preview & editing endpoints (ui-design.md Page 3).

``GET /proposals/{id}`` returns the proposal aggregate (current version + locked
structure) for the side-by-side preview. ``POST /proposals/{id}/versions`` applies
a **text-only** edit: prose ``body`` changes within existing blocks only — headings,
section ids, order, and the template are locked, enforced server-side by the
``EditProposal`` use-case (structure violations and unknown sections are 4xx).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response

from app.api.schemas.generation import EditRequest, ExportHtmlRequest, ProposalDTO
from app.container import Container, get_container
from app.modules.proposal_generation.export.export import (
    ExportBlockedError,
    ExportFormat,
    ExportProposalCommand,
)
from app.modules.proposal_generation.export.export import (
    ProposalNotFoundError as ExportProposalNotFoundError,
)
from app.modules.proposal_generation.export.render import render_document_page
from app.modules.proposal_generation.versioning.edit import (
    EditProposalCommand,
    ProposalNotFoundError,
    StructureLockError,
    UnknownSectionError,
)

router = APIRouter(prefix="/proposals", tags=["proposals"])

ContainerDep = Annotated[Container, Depends(get_container)]


@router.get("/{proposal_id}", response_model=ProposalDTO)
async def get_proposal(proposal_id: str, container: ContainerDep) -> ProposalDTO:
    async with container.unit_of_work() as uow:
        proposal = await uow.proposals.get(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail=f"proposal {proposal_id!r} not found")
    return ProposalDTO.from_domain(proposal)


@router.post("/{proposal_id}/versions", response_model=ProposalDTO)
async def edit_proposal(
    proposal_id: str,
    body: EditRequest,
    container: ContainerDep,
    x_requested_by: Annotated[str | None, Header()] = None,
) -> ProposalDTO:
    command = EditProposalCommand(
        proposal_id=proposal_id,
        edits={edit.section_id: edit.body for edit in body.edits},
        edited_by=x_requested_by or "user",
    )
    try:
        proposal = await container.edit_proposal().execute(command)
    except ProposalNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"proposal {proposal_id!r} not found") from exc
    except UnknownSectionError as exc:
        raise HTTPException(status_code=400, detail=f"unknown section(s): {exc}") from exc
    except StructureLockError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ProposalDTO.from_domain(proposal)


@router.get("/{proposal_id}/document", response_class=Response)
async def get_proposal_document(proposal_id: str, container: ContainerDep) -> Response:
    """The proposal as a styled, editable HTML page (company template, no metrics).

    Loaded by the WYSIWYG preview editor; the user edits this in place and the export
    endpoints below convert exactly what was edited.
    """
    async with container.unit_of_work() as uow:
        proposal = await uow.proposals.get(proposal_id)
        if proposal is None:
            raise HTTPException(status_code=404, detail=f"proposal {proposal_id!r} not found")
        event = await uow.audit.get(proposal.gen_id)
    return Response(content=render_document_page(proposal, event), media_type="text/html")


async def _run_export(
    container: Container, proposal_id: str, fmt: ExportFormat, html: str | None
) -> Response:
    command = ExportProposalCommand(proposal_id=proposal_id, fmt=fmt, html=html)
    try:
        result = await container.export_proposal().execute(command)
    except ExportProposalNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"proposal {proposal_id!r} not found") from exc
    except ExportBlockedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Response(
        content=result.content,
        media_type=result.media_type,
        headers={"Content-Disposition": f'attachment; filename="{result.filename}"'},
    )


@router.get("/{proposal_id}/export")
async def export_proposal(
    proposal_id: str,
    container: ContainerDep,
    format: Annotated[ExportFormat, Query()] = ExportFormat.MARKDOWN,
) -> Response:
    """Render the stored proposal in the company template and mark it exported.

    The information-loss gate governs availability: a run leaning on financial
    evidence above the extraction-gate loss ceiling is blocked (409).
    """
    return await _run_export(container, proposal_id, format, html=None)


@router.post("/{proposal_id}/export")
async def export_proposal_edited(
    proposal_id: str,
    body: ExportHtmlRequest,
    container: ContainerDep,
    format: Annotated[ExportFormat, Query()] = ExportFormat.PDF,
) -> Response:
    """Convert the editor's current HTML to PDF/DOCX (or HTML) and mark it exported.

    Same information-loss gate as the GET form; the difference is the body is rendered
    from the posted, user-edited HTML rather than the stored proposal.
    """
    return await _run_export(container, proposal_id, format, html=body.html)
