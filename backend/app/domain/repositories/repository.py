"""Repository identity, generation role, and the classifier soft distribution.

The platform's central design rule: three governed repositories, each with a
**distinct role**, never merged into one global ranking (rag-design.md). This
module is the canonical vocabulary for *which* repository and *what role* it
plays — every chunk, retrieval candidate, and contribution metric references it.

Collection names follow ARCHITECTURE_SUMMARY.md (the source of truth):
``repo_financial`` · ``repo_proposals`` · ``repo_templates``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Repository(StrEnum):
    """The three governed knowledge repositories."""

    FINANCIAL = "financial"
    PROPOSAL = "proposal"
    TEMPLATE = "template"


class RoleInGeneration(StrEnum):
    """The role a repository's content plays in a generated proposal.

    Drives assembly precedence, ranking, and the citation/leakage rules. Only
    ``EVIDENCE`` (financial) may become a citation.
    """

    EVIDENCE = "evidence"
    EXEMPLAR = "exemplar"
    SCAFFOLD = "scaffold"


# Canonical ChromaDB collection name per repository.
COLLECTION_NAMES: dict[Repository, str] = {
    Repository.FINANCIAL: "repo_financial",
    Repository.PROPOSAL: "repo_proposals",
    Repository.TEMPLATE: "repo_templates",
}

# Fixed repository → role mapping (a repository's role is intrinsic, not per-query).
REPOSITORY_ROLE: dict[Repository, RoleInGeneration] = {
    Repository.FINANCIAL: RoleInGeneration.EVIDENCE,
    Repository.PROPOSAL: RoleInGeneration.EXEMPLAR,
    Repository.TEMPLATE: RoleInGeneration.SCAFFOLD,
}


def collection_name(repository: Repository) -> str:
    """Canonical ChromaDB collection name for a repository."""
    return COLLECTION_NAMES[repository]


def role_of(repository: Repository) -> RoleInGeneration:
    """The generation role intrinsic to a repository."""
    return REPOSITORY_ROLE[repository]


@dataclass(frozen=True, slots=True)
class SoftDistribution:
    """Classifier output ``π_d = (π_FIN, π_PROP, π_TMPL)`` with Σ = 1.

    Used for routing (argmax + thresholds) and for Corpus Contribution scoring
    (document-intelligence.md U-5). Persisted to lineage with every document.
    """

    financial: float
    proposal: float
    template: float

    def __post_init__(self) -> None:
        total = self.financial + self.proposal + self.template
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"π_d must sum to 1.0 (got {total!r})")
        for name, value in (
            ("financial", self.financial),
            ("proposal", self.proposal),
            ("template", self.template),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"π_d.{name} must be in [0, 1] (got {value!r})")

    def as_mapping(self) -> dict[Repository, float]:
        return {
            Repository.FINANCIAL: self.financial,
            Repository.PROPOSAL: self.proposal,
            Repository.TEMPLATE: self.template,
        }

    @property
    def argmax(self) -> Repository:
        """The most-probable repository (routing target)."""
        return max(self.as_mapping().items(), key=lambda kv: kv[1])[0]

    @property
    def confidence(self) -> float:
        """conf = max(π_d) — the classification confidence / soft gate signal."""
        return max(self.financial, self.proposal, self.template)
