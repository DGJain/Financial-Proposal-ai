"""Request/response DTOs for the generation & preview API.

These pydantic models are the HTTP contract the frontend's generated client binds
to (backend OpenAPI → ``frontend/src/api``). They mirror the domain shapes but are
deliberately separate: the domain stays free of serialization concerns, and the
wire format can evolve without touching use-cases. ``from_domain`` factories keep
the mapping in one place.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.generation.generation_event import GenerationEvent
from app.domain.metrics.contribution import ContributionBreakdown, RepositoryShare
from app.domain.proposals.enums import ConfidenceBand, GenerationOutcome, ProposalStatus
from app.domain.proposals.proposal import Proposal, ProposalVersion


# --- requests ----------------------------------------------------------------


class AttachmentDTO(BaseModel):
    """A piece of user-supplied context (a pasted note or an attached text file)."""

    name: str
    text: str


class GenerateRequest(BaseModel):
    """A proposal brief. The caller's ACL/engagement arrives via ``X-*`` headers.

    ``query`` is the chat-style free-text ask; ``attachments`` are text/markdown
    files the user attached on the composer. Both are folded into the brief's
    framing instructions (and recorded verbatim as the run's prompt) — they shape
    the prose but never become citable evidence (only ``repo_financial`` can).
    """

    title: str = Field(min_length=1)
    proposal_type: str = Field(min_length=1)
    entity: str | None = None
    fiscal_year: int | None = None
    sector: str | None = None
    line_items: list[str] = Field(default_factory=list)
    instructions: str = ""
    query: str = ""
    attachments: list[AttachmentDTO] = Field(default_factory=list)

    def composed_instructions(self) -> str:
        """Merge query + manual instructions + attachment text into one block."""
        parts: list[str] = []
        if self.query.strip():
            parts.append(self.query.strip())
        if self.instructions.strip():
            parts.append(self.instructions.strip())
        for att in self.attachments:
            if att.text.strip():
                parts.append(f"[Attached context — {att.name}]\n{att.text.strip()}")
        return "\n\n".join(parts)

    def framing_instructions(self) -> str:
        """Query + manual instructions only — attachments ride on the brief separately
        (so their content/figures get the client-supplied treatment, not just framing)."""
        parts: list[str] = []
        if self.query.strip():
            parts.append(self.query.strip())
        if self.instructions.strip():
            parts.append(self.instructions.strip())
        return "\n\n".join(parts)


class AttachmentExtractResponse(BaseModel):
    """Server-side text extracted from one uploaded binary (PDF/DOCX/PPTX/image).

    The composer posts a file's raw bytes and gets back its text so it can ride
    along as ``query`` context — exactly like a pasted note. ``extracted`` is
    ``False`` (with a human ``detail``) when the format needs a library/binary that
    isn't available here (e.g. image OCR); the UI then attaches the file by name
    only. Extracted text is context for the prose — never citable evidence (only
    ``repo_financial`` is)."""

    name: str
    text: str = ""
    extracted: bool = False
    char_count: int = 0
    detail: str = ""


class SectionEdit(BaseModel):
    """A prose-only edit to one existing section (structure stays locked)."""

    section_id: str
    body: str


class EditRequest(BaseModel):
    edits: list[SectionEdit] = Field(min_length=1)


class ExportHtmlRequest(BaseModel):
    """The HTML the WYSIWYG editor currently shows — converted on export so the
    PDF/DOCX matches what the user edited on screen."""

    html: str = Field(min_length=1)


# --- response components -----------------------------------------------------


class RepositoryShareDTO(BaseModel):
    financial: float
    proposal: float
    template: float

    @classmethod
    def from_domain(cls, share: RepositoryShare) -> RepositoryShareDTO:
        return cls(
            financial=share.financial, proposal=share.proposal, template=share.template
        )


class ContributionDTO(BaseModel):
    context_share: RepositoryShareDTO
    factual_share: RepositoryShareDTO

    @classmethod
    def from_domain(cls, contribution: ContributionBreakdown) -> ContributionDTO:
        return cls(
            context_share=RepositoryShareDTO.from_domain(contribution.context_share),
            factual_share=RepositoryShareDTO.from_domain(contribution.factual_share),
        )


class ConfidenceDTO(BaseModel):
    score: float
    band: ConfidenceBand


class CitationDTO(BaseModel):
    claim_ordinal: int
    source_name: str
    page: int


class SectionDTO(BaseModel):
    section_id: str
    slot: str
    heading: str
    order: int
    body: str


class ProposalDTO(BaseModel):
    proposal_id: str
    gen_id: str
    engagement_id: str
    template_id: str
    status: ProposalStatus
    version_no: int
    sections: list[SectionDTO]

    @classmethod
    def from_domain(cls, proposal: Proposal) -> ProposalDTO:
        version: ProposalVersion = proposal.current_version
        return cls(
            proposal_id=proposal.proposal_id,
            gen_id=proposal.gen_id,
            engagement_id=proposal.engagement_id,
            template_id=proposal.template_id,
            status=proposal.status,
            version_no=version.version_no,
            sections=[
                SectionDTO(
                    section_id=s.section_id,
                    slot=s.slot,
                    heading=s.heading,
                    order=s.order,
                    body=s.body,
                )
                for s in version.sections
            ],
        )


class GenerateResponse(BaseModel):
    """The synchronous result of one generation run."""

    report_id: str  # gen_id — opens the Execution Report (Phase 5)
    outcome: GenerationOutcome
    confidence: ConfidenceDTO
    contribution: ContributionDTO | None = None
    citations: list[CitationDTO] = Field(default_factory=list)
    proposal: ProposalDTO | None = None  # absent on refusal/block
    refusal_reason: str | None = None

    @classmethod
    def from_domain(
        cls, event: GenerationEvent, proposal: Proposal | None
    ) -> GenerateResponse:
        return cls(
            report_id=event.gen_id,
            outcome=event.outcome,
            confidence=ConfidenceDTO(score=event.confidence, band=event.confidence_band),
            contribution=(
                ContributionDTO.from_domain(event.contribution)
                if event.contribution is not None
                else None
            ),
            citations=[
                CitationDTO(
                    claim_ordinal=c.claim_ordinal, source_name=c.source_name, page=c.page
                )
                for c in event.citations
            ],
            proposal=ProposalDTO.from_domain(proposal) if proposal is not None else None,
            refusal_reason=event.refusal_reason,
        )
