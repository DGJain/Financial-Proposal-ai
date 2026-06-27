"""Generation inputs — the proposal brief and the requesting caller's context.

A run starts from a **brief** (what proposal to write, for which entity/period,
grounding which line items) plus the **requester context** (the engagement and
ACL grants that scope every retrieval). These are pure value objects at the
use-case boundary: the brief drives per-repository query formulation
(rag-design.md §1), and the requester context becomes the ``AclFilter`` that
pre-filters all three branches (architecture.md "deal-team walls").
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class BriefAttachment:
    """A user-supplied file's extracted text (PDF/DOCX/…) attached on the composer.

    Attachments are *client-supplied content*: their text and data tables may be
    woven into the generated proposal and their figures are allowed through the
    numeric gate (labelled unverified) — but a figure absent from every attachment
    and from cited evidence is still treated as invented and blocked.
    """

    name: str
    text: str


@dataclass(frozen=True, slots=True)
class GenerationBrief:
    """What to generate and the facts that scope its evidence retrieval.

    ``entity``/``fiscal_year`` scope the financial (evidence) branch — wrong-period
    or wrong-entity evidence is *dropped*, not down-weighted. ``proposal_type`` and
    ``sector`` scope the exemplar and scaffold branches. ``line_items`` name the
    figures the proposal must ground (revenue, net income…), so the assembler can
    prioritise the evidence that fills them.
    """

    title: str
    proposal_type: str  # e.g. "statement_of_work", "pitch" — matches template/exemplar
    entity: str | None = None  # issuer/client the engagement is about
    fiscal_year: int | None = None
    sector: str | None = None
    line_items: tuple[str, ...] = ()  # figures to ground, e.g. ("revenue", "net income")
    instructions: str = ""  # free-text guidance for framing
    attachments: tuple[BriefAttachment, ...] = ()  # client-supplied content/data

    @property
    def has_attachments(self) -> bool:
        """True if any attachment carries usable extracted text."""
        return any(a.text.strip() for a in self.attachments)

    def attachment_text(self) -> str:
        """All attachment text concatenated — the client material to weave in."""
        return "\n\n".join(
            f"[Attached content — {a.name}]\n{a.text.strip()}"
            for a in self.attachments
            if a.text.strip()
        )

    def render_prompt(self) -> str:
        """A stable textual rendering recorded as ``GenerationEvent.prompt``."""
        parts = [f"Proposal: {self.title}", f"Type: {self.proposal_type}"]
        if self.entity:
            parts.append(f"Entity: {self.entity}")
        if self.fiscal_year is not None:
            parts.append(f"Fiscal year: {self.fiscal_year}")
        if self.sector:
            parts.append(f"Sector: {self.sector}")
        if self.line_items:
            parts.append(f"Line items: {', '.join(self.line_items)}")
        if self.instructions:
            parts.append(f"Instructions: {self.instructions}")
        for a in self.attachments:
            if a.text.strip():
                parts.append(f"[Attached context — {a.name}]\n{a.text.strip()}")
        return "\n".join(parts)


@dataclass(frozen=True, slots=True)
class RequesterContext:
    """The caller's identity and grants — the source of the retrieval ACL filter.

    ``engagement_id`` is the deal-team wall the financial branch is scoped to;
    ``caller_groups`` are the RBAC groups matched fail-closed at retrieval.
    """

    engagement_id: str | None = None
    caller_groups: frozenset[str] = field(default_factory=frozenset)
    classification: str | None = None
    requested_by: str = "system"
