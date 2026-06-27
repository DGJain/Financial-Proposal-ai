"""Proposal aggregate — the generated document and its edit versions.

The editing contract (ui-design.md Page 3): structure & template are locked —
headings, section IDs, and section order are immutable; only the prose ``body``
within an existing block may change, and each change produces a new
``ProposalVersion``. This keeps every sentence traceable and the chosen template
intact for export.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.domain.proposals.enums import ProposalStatus


@dataclass(frozen=True, slots=True)
class ProposalSection:
    """One section of a proposal, bound to a template ``section_slot``.

    ``heading``, ``section_id``, ``order``, and ``slot`` are structural and
    locked; only ``body`` is editable.
    """

    section_id: str
    slot: str  # template section_slot this section fills
    heading: str
    order: int
    body: str

    def with_body(self, new_body: str) -> ProposalSection:
        """Return a copy with edited prose; structure is preserved unchanged."""
        return ProposalSection(
            section_id=self.section_id,
            slot=self.slot,
            heading=self.heading,
            order=self.order,
            body=new_body,
        )


@dataclass(frozen=True, slots=True)
class ProposalVersion:
    """An immutable snapshot of the proposal's prose at a point in time."""

    version_no: int
    sections: tuple[ProposalSection, ...]
    created_ts: datetime
    created_by: str
    status: ProposalStatus

    def section_structure(self) -> tuple[tuple[str, int], ...]:
        """The locked structural signature: (section_id, order) pairs."""
        return tuple((s.section_id, s.order) for s in self.sections)


@dataclass(frozen=True, slots=True)
class Proposal:
    """Aggregate root linking a generation run to its versioned content."""

    proposal_id: str
    gen_id: str
    engagement_id: str
    template_id: str
    versions: tuple[ProposalVersion, ...]
    status: ProposalStatus = ProposalStatus.DRAFT

    @property
    def current_version(self) -> ProposalVersion:
        return max(self.versions, key=lambda v: v.version_no)

    def structure_locked_against(self, candidate: ProposalVersion) -> bool:
        """Validate a proposed edit kept structure/template intact.

        Returns True iff the candidate version has the identical structural
        signature as the current version (same sections, same order) — the
        invariant the side-by-side editor must never violate.
        """
        return candidate.section_structure() == self.current_version.section_structure()
