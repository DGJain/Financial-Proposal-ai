"""Repository contribution metrics (document-intelligence.md U-5, rag-design.md §6).

Two distinct families, both per-repository and each summing to 100%:

- **Corpus / Context Contribution** — composition of the knowledge base / share
  of the assembled context per repository.
- **Generation / Factual Contribution** — lineage-based share of grounded claims
  cited to each repository. By the hard rule this is ~100% financial; any
  non-financial factual share is the signature of figure leakage and triggers a
  block-and-regenerate guardrail.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.repositories.repository import Repository


@dataclass(frozen=True, slots=True)
class RepositoryShare:
    """A per-repository percentage triple that sums to ~100%."""

    financial: float
    proposal: float
    template: float

    def __post_init__(self) -> None:
        total = self.financial + self.proposal + self.template
        # Allow an all-zero share for refused runs (no contribution at all).
        if total != 0.0 and abs(total - 100.0) > 0.5:
            raise ValueError(f"repository shares must sum to ~100% (got {total!r})")

    def get(self, repository: Repository) -> float:
        return {
            Repository.FINANCIAL: self.financial,
            Repository.PROPOSAL: self.proposal,
            Repository.TEMPLATE: self.template,
        }[repository]


@dataclass(frozen=True, slots=True)
class ContributionBreakdown:
    """Both contribution families for one generation event.

    ``context_share`` captures how much each repository shaped the input;
    ``factual_share`` captures how much factual weight each carried. The health
    check compares ``factual_share.financial`` against its floor.
    """

    context_share: RepositoryShare
    factual_share: RepositoryShare

    def factual_health_ok(self, *, min_financial_factual_share_pct: float) -> bool:
        """True iff financial carries ~all factual weight (no figure leakage)."""
        return self.factual_share.financial >= min_financial_factual_share_pct
