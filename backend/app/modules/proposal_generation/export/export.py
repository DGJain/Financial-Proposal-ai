"""Export a proposal as a self-contained document (ui-design.md §6.4).

Renders the locked template plus embedded lineage metadata and marks the proposal
``EXPORTED``. The **information-loss gate governs whether export is enabled**: the
run's retrieved financial evidence must sit within the financial extraction gate
(EQS ≥ 0.90 ⇒ loss ≤ 10%); a run leaning on higher-loss evidence is blocked, the
same governance that keeps low-quality numbers out of the corpus. Re-ingestion of
an exported proposal into ``repo_proposals`` remains the existing Phase-2 curation
gate — export here is render + lifecycle only.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from app.core.policies.quality_gates import DEFAULT_QUALITY_GATE_POLICY
from app.domain.ports.unit_of_work import UnitOfWorkPort
from app.domain.proposals.enums import ProposalStatus
from app.modules.proposal_generation.export.render import (
    render_docx,
    render_docx_from_html,
    render_html,
    render_html_document,
    render_markdown,
    render_pdf,
    render_pdf_from_html,
)
from app.modules.reporting.quality import aggregate_financial_quality

# The financial extraction gate ceiling expressed as a max information-loss %.
_DEFAULT_MAX_INFORMATION_LOSS_PCT = round(
    (1.0 - DEFAULT_QUALITY_GATE_POLICY.financial_gate.min_eqs) * 100.0, 2
)


class ExportFormat(StrEnum):
    MARKDOWN = "markdown"
    HTML = "html"
    PDF = "pdf"
    DOCX = "docx"


class ProposalNotFoundError(LookupError):
    """Raised when the proposal to export does not exist."""


class ExportBlockedError(RuntimeError):
    """Raised when the information-loss gate disables export for a proposal."""


@dataclass(frozen=True, slots=True)
class ExportProposalCommand:
    proposal_id: str
    fmt: ExportFormat = ExportFormat.MARKDOWN
    # The WYSIWYG editor posts back the HTML the user actually edited; when present
    # (pdf/docx/html only) the export converts *that* so the file matches the screen.
    html: str | None = None


@dataclass(frozen=True, slots=True)
class ExportResult:
    content: bytes
    media_type: str
    filename: str
    status: ProposalStatus


# format → (stored-renderer, edited-html-renderer, media_type, extension).
# Stored renderers render the saved proposal; html renderers convert the editor's
# posted HTML. Text outputs return str (encoded below); pdf/docx return bytes.
_DOCX_CT = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_RENDERERS = {
    ExportFormat.MARKDOWN: (render_markdown, None, "text/markdown", "md"),
    ExportFormat.HTML: (render_html, render_html_document, "text/html", "html"),
    ExportFormat.PDF: (render_pdf, render_pdf_from_html, "application/pdf", "pdf"),
    ExportFormat.DOCX: (render_docx, render_docx_from_html, _DOCX_CT, "docx"),
}


class ExportProposal:
    """Render a proposal + lineage and advance it to ``EXPORTED``."""

    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWorkPort],
        *,
        max_information_loss_pct: float = _DEFAULT_MAX_INFORMATION_LOSS_PCT,
    ) -> None:
        self._uow_factory = uow_factory
        self._max_information_loss_pct = max_information_loss_pct

    async def execute(self, command: ExportProposalCommand) -> ExportResult:
        async with self._uow_factory() as uow:
            proposal = await uow.proposals.get(command.proposal_id)
            if proposal is None:
                raise ProposalNotFoundError(command.proposal_id)

            event = await uow.audit.get(proposal.gen_id)
            quality = (
                await aggregate_financial_quality(event, uow.lineage)
                if event is not None
                else None
            )
            if quality is not None and quality.information_loss_pct > self._max_information_loss_pct:
                raise ExportBlockedError(
                    f"information loss {quality.information_loss_pct:.1f}% exceeds the "
                    f"export ceiling of {self._max_information_loss_pct:.1f}%"
                )

            stored_renderer, html_renderer, media_type, ext = _RENDERERS[command.fmt]
            if command.html is not None and html_renderer is not None:
                rendered = html_renderer(command.html)
            else:
                rendered = stored_renderer(proposal, event)
            content = rendered.encode("utf-8") if isinstance(rendered, str) else rendered

            await uow.proposals.set_status(command.proposal_id, ProposalStatus.EXPORTED)
            await uow.commit()

        return ExportResult(
            content=content,
            media_type=media_type,
            filename=f"{command.proposal_id}.{ext}",
            status=ProposalStatus.EXPORTED,
        )
