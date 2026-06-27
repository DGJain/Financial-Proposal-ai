"""Federated retrieval & context-budget policy.

Encodes the per-branch candidate budgets and the two-stage ranking rule from
rag-design.md (§1, §4): rank *within* each repository, then allocate a context
budget by configurable weight — never pool all three by raw score. A default
profile weights evidence highest, reserves a fixed scaffold slot for the
template, and gives exemplars a bounded share. Recorded with each generation
event for auditability.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BranchBudget:
    """Per-branch retrieval candidate budget (the *k* of each fan-out branch)."""

    financial_k: int = 40  # evidence: high recall, the only citable branch
    proposal_k: int = 8  # exemplars: medium k
    template_k: int = 1  # scaffold: near-deterministic, often top-1


@dataclass(frozen=True, slots=True)
class ContextBudget:
    """Share of the assembled-context token budget guaranteed to each role.

    Fractions sum to 1.0. Evidence gets the largest guaranteed share, the
    scaffold a fixed slot, exemplars a bounded share so style never crowds out
    facts. ``total_context_tokens`` is sized against the *smaller* production SLM
    window so the assembler never relies on a larger prototype window.
    """

    total_context_tokens: int = 8192
    evidence_share: float = 0.60  # financial
    exemplar_share: float = 0.25  # proposal
    scaffold_share: float = 0.15  # template


@dataclass(frozen=True, slots=True)
class GroundingPolicy:
    """Financial grounding gate (the floor) + grounding-loop bounds.

    A strong template/exemplar cannot rescue weak factual grounding
    (rag-design.md §5). Below the floor the system re-enters the grounding loop
    on the financial branch up to ``max_grounding_loops`` times, then refuses —
    preserving "refuse rather than answer outside the corpus."
    """

    grounding_floor: float = 0.60  # min financial grounding strength to proceed
    high_confidence_band: float = 0.80  # ≥ → generate cited
    max_grounding_loops: int = 2
    # Factual-contribution health check (rag-design.md §6b): financial factual
    # share must be ~100%. Below this floor → block & regenerate (figure leakage).
    min_financial_factual_share: float = 0.999
    max_regeneration_attempts: int = 1


@dataclass(frozen=True, slots=True)
class RetrievalPolicy:
    branch_budget: BranchBudget
    context_budget: ContextBudget
    grounding: GroundingPolicy


DEFAULT_RETRIEVAL_POLICY = RetrievalPolicy(
    branch_budget=BranchBudget(),
    context_budget=ContextBudget(),
    grounding=GroundingPolicy(),
)
