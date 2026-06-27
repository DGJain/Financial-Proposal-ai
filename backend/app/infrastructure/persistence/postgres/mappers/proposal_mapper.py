"""Translation between the ``Proposal`` aggregate and its ORM rows.

On read, versions and sections are re-sorted into their canonical order
(version_no, section order) so the reconstructed aggregate is byte-identical and
the structure-lock check is stable.
"""

from __future__ import annotations

from app.domain.proposals.enums import ProposalStatus
from app.domain.proposals.proposal import Proposal, ProposalSection, ProposalVersion
from app.infrastructure.persistence.postgres.models.proposal import (
    ProposalRow,
    ProposalSectionRow,
    ProposalVersionRow,
)


def to_row(proposal: Proposal) -> ProposalRow:
    row = ProposalRow(
        proposal_id=proposal.proposal_id,
        gen_id=proposal.gen_id,
        engagement_id=proposal.engagement_id,
        template_id=proposal.template_id,
        status=proposal.status.value,
    )
    row.versions = [
        ProposalVersionRow(
            version_no=v.version_no,
            created_ts=v.created_ts,
            created_by=v.created_by,
            status=v.status.value,
            sections=[
                ProposalSectionRow(
                    section_id=s.section_id,
                    slot=s.slot,
                    heading=s.heading,
                    order=s.order,
                    body=s.body,
                )
                for s in v.sections
            ],
        )
        for v in proposal.versions
    ]
    return row


def to_domain(row: ProposalRow) -> Proposal:
    versions = tuple(
        ProposalVersion(
            version_no=v.version_no,
            sections=tuple(
                ProposalSection(
                    section_id=s.section_id,
                    slot=s.slot,
                    heading=s.heading,
                    order=s.order,
                    body=s.body,
                )
                for s in sorted(v.sections, key=lambda s: s.order)
            ),
            created_ts=v.created_ts,
            created_by=v.created_by,
            status=ProposalStatus(v.status),
        )
        for v in sorted(row.versions, key=lambda v: v.version_no)
    )
    return Proposal(
        proposal_id=row.proposal_id,
        gen_id=row.gen_id,
        engagement_id=row.engagement_id,
        template_id=row.template_id,
        versions=versions,
        status=ProposalStatus(row.status),
    )
