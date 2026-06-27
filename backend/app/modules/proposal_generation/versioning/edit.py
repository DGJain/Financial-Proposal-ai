"""Text-only proposal editing (ui-design.md Page 3 / §6.4).

The editing contract is the platform's traceability guarantee: **structure and
template are locked** — headings, section ids, and section order are immutable;
only the prose ``body`` within an existing block may change, and every change
produces a new immutable ``ProposalVersion``. This use-case enforces that
invariant server-side (the UI also hides structural controls, but the gate lives
here): edits are keyed by ``section_id`` and applied with ``ProposalSection.with_body``,
then the candidate version is validated against ``Proposal.structure_locked_against``
before it is appended.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from app.domain.ports.unit_of_work import UnitOfWorkPort
from app.domain.proposals.enums import ProposalStatus
from app.domain.proposals.proposal import Proposal, ProposalVersion


class ProposalNotFoundError(LookupError):
    """Raised when the target proposal does not exist."""


class StructureLockError(ValueError):
    """Raised when an edit would alter locked structure/template."""


class UnknownSectionError(ValueError):
    """Raised when an edit targets a section id that is not in the proposal."""


@dataclass(frozen=True, slots=True)
class EditProposalCommand:
    proposal_id: str
    edits: Mapping[str, str]  # section_id -> new body
    edited_by: str = "user"


class EditProposal:
    """Applies prose-only edits and appends a structure-locked new version."""

    def __init__(self, uow_factory: Callable[[], UnitOfWorkPort]) -> None:
        self._uow_factory = uow_factory

    async def execute(self, command: EditProposalCommand) -> Proposal:
        async with self._uow_factory() as uow:
            proposal = await uow.proposals.get(command.proposal_id)
            if proposal is None:
                raise ProposalNotFoundError(command.proposal_id)

            candidate = self._apply(proposal, command)
            if not proposal.structure_locked_against(candidate):
                # Defensive: only bodies were touched, so this should never trip —
                # it is the last line of defence for the traceability guarantee.
                raise StructureLockError(
                    "edit would alter locked structure or template"
                )

            await uow.proposals.add_version(command.proposal_id, candidate)
            await uow.commit()

        # Reconstruct the aggregate with the appended version for the caller.
        return Proposal(
            proposal_id=proposal.proposal_id,
            gen_id=proposal.gen_id,
            engagement_id=proposal.engagement_id,
            template_id=proposal.template_id,
            versions=(*proposal.versions, candidate),
            status=candidate.status,
        )

    def _apply(self, proposal: Proposal, command: EditProposalCommand) -> ProposalVersion:
        current = proposal.current_version
        known = {s.section_id for s in current.sections}
        unknown = set(command.edits) - known
        if unknown:
            raise UnknownSectionError(", ".join(sorted(unknown)))

        sections = tuple(
            s.with_body(command.edits[s.section_id]) if s.section_id in command.edits else s
            for s in current.sections
        )
        return ProposalVersion(
            version_no=current.version_no + 1,
            sections=sections,
            created_ts=datetime.now(UTC),
            created_by=command.edited_by,
            status=ProposalStatus.EDITED,
        )
