"""Repository contribution metrics (rag-design.md §6b).

Two per-repository shares, each summing to 100% (or all-zero for a refusal):

* **context share** — assembled-context tokens per repository ÷ total. How much
  each repository *shaped* the proposal's input.
* **factual share** — grounded claims cited to each repository ÷ total. By the
  hard rule this is ~100% financial; any non-financial factual share is the
  signature of figure leakage and is what the factual-health guardrail trips on.

Percentages are computed so the triple sums to exactly 100.0 (the template gets
the residual), satisfying ``RepositoryShare``'s invariant without float drift.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.domain.metrics.contribution import ContributionBreakdown, RepositoryShare
from app.domain.repositories.repository import Repository

_ZERO = RepositoryShare(financial=0.0, proposal=0.0, template=0.0)


class ContributionCalculator:
    def compute(
        self,
        *,
        context_tokens: Mapping[Repository, int],
        factual_counts: Mapping[Repository, int],
    ) -> ContributionBreakdown:
        return ContributionBreakdown(
            context_share=_share(context_tokens),
            factual_share=_share(factual_counts),
        )


def _share(counts: Mapping[Repository, int]) -> RepositoryShare:
    fin = max(0, counts.get(Repository.FINANCIAL, 0))
    prop = max(0, counts.get(Repository.PROPOSAL, 0))
    tmpl = max(0, counts.get(Repository.TEMPLATE, 0))
    total = fin + prop + tmpl
    if total == 0:
        return _ZERO
    financial_pct = fin / total * 100.0
    proposal_pct = prop / total * 100.0
    # Residual to template so the triple sums to exactly 100.0.
    template_pct = 100.0 - financial_pct - proposal_pct
    return RepositoryShare(
        financial=round(financial_pct, 6),
        proposal=round(proposal_pct, 6),
        template=round(max(0.0, template_pct), 6),
    )
