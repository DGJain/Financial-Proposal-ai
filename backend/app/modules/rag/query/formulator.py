"""Per-repository query formulation (rag-design.md §1).

One brief fans out into **three differently-shaped queries**, because each
repository is searched for a different reason:

* **financial (evidence)** — entity, fiscal period and the line items to ground;
  the period/entity become a *hard* ranking constraint downstream, so the query
  text leads with them. ``where`` is left broad here (engagement scoping is the
  ACL pre-filter) so the grounding loop has room to relax.
* **proposal (exemplar)** — proposal type, sector and approach; retrieved for
  *how to say it*. Exemplars are already anonymized at ingestion, so no extra
  filter is needed.
* **template (scaffold)** — proposal type and required sections; filtered to
  ``status=approved`` so only released scaffolds are used, and kept near-top-1.

Pure and deterministic: the same brief always yields the same three queries,
which is what makes the Execution Report replayable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.generation.brief import GenerationBrief
from app.domain.repositories.repository import Repository


@dataclass(frozen=True, slots=True)
class BranchQuery:
    """A single repository's formulated query: its embed text + metadata filter."""

    repository: Repository
    text: str
    where: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BranchQueries:
    """The three role-shaped queries produced from one brief."""

    financial: BranchQuery
    proposal: BranchQuery
    template: BranchQuery

    def all(self) -> tuple[BranchQuery, BranchQuery, BranchQuery]:
        return (self.financial, self.proposal, self.template)


class QueryFormulator:
    """Turns a brief into three per-repository :class:`BranchQuery` objects."""

    def formulate(self, brief: GenerationBrief) -> BranchQueries:
        return BranchQueries(
            financial=self._financial(brief),
            proposal=self._proposal(brief),
            template=self._template(brief),
        )

    def _financial(self, brief: GenerationBrief) -> BranchQuery:
        # Lead with the engagement entity/period/line items — the evidence the
        # proposal must be grounded on. Period/entity are enforced as a hard match
        # in ranking (dropped, not down-weighted), not pushed into ``where`` here.
        terms: list[str] = []
        if brief.entity:
            terms.append(brief.entity)
        if brief.fiscal_year is not None:
            terms.append(f"fiscal year {brief.fiscal_year}")
        terms.extend(brief.line_items)
        terms.append(brief.title)
        return BranchQuery(repository=Repository.FINANCIAL, text=" ".join(terms), where={})

    def _proposal(self, brief: GenerationBrief) -> BranchQuery:
        terms = [brief.proposal_type]
        if brief.sector:
            terms.append(brief.sector)
        terms.append(brief.title)
        if brief.instructions:
            terms.append(brief.instructions)
        return BranchQuery(repository=Repository.PROPOSAL, text=" ".join(terms), where={})

    def _template(self, brief: GenerationBrief) -> BranchQuery:
        terms = [brief.proposal_type]
        if brief.sector:
            terms.append(brief.sector)
        # Only released scaffolds — never a draft/deprecated template skeleton.
        return BranchQuery(
            repository=Repository.TEMPLATE,
            text=" ".join(terms),
            where={"status": "approved"},
        )
