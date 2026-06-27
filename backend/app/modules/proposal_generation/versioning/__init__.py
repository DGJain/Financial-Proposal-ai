"""Text-only, structure-locked proposal editing/versioning."""

from app.modules.proposal_generation.versioning.edit import (
    EditProposal,
    EditProposalCommand,
    ProposalNotFoundError,
    StructureLockError,
    UnknownSectionError,
)

__all__ = [
    "EditProposal",
    "EditProposalCommand",
    "ProposalNotFoundError",
    "StructureLockError",
    "UnknownSectionError",
]
