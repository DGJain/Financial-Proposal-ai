"""Proposal lifecycle and exemplar vocabulary."""

from __future__ import annotations

from enum import StrEnum


class ProposalStatus(StrEnum):
    """Lifecycle of a generated proposal.

    ``v1`` is saved as ``DRAFT`` after the retention gate; side-by-side edits
    create new versions; ``APPROVED`` enables audited export and re-ingestion
    into ``repo_proposals`` (the curation feedback loop).
    """

    DRAFT = "draft"
    EDITED = "edited"
    APPROVED = "approved"
    EXPORTED = "exported"


class GenerationOutcome(StrEnum):
    """Outcome shown in Prompt History (ui-design.md §5.A).

    ✓ ``GENERATED`` (grounded, cited) · ◐ ``STYLE_ONLY`` · ◐ ``DRAFT`` ·
    ✕ ``REFUSED``. A refused run still produces an Execution Report (zero docs,
    refusal reason, no generation stages).

    ``STYLE_ONLY`` is the no-evidence fallback: when nothing clears the financial
    grounding floor but a template/exemplars exist, the platform produces a
    **figure-free** draft styled on past proposals rather than refusing outright.
    It carries **zero citations** and ``LOW`` confidence — the anti-hallucination
    guarantee holds because the draft asserts no numeric figures at all.
    """

    GENERATED = "generated"
    STYLE_ONLY = "style_only"
    DRAFT = "draft"
    REFUSED = "refused"


class Outcome(StrEnum):
    """Win/loss signal on exemplar proposals; boosts ranking toward winners."""

    WON = "won"
    LOST = "lost"
    PENDING = "pending"


class ConfidenceBand(StrEnum):
    """Banding of the gated confidence composite (rag-design.md §5)."""

    HIGH = "high"  # generate · cited
    MEDIUM = "medium"  # generate · flag low-confidence sections
    LOW = "low"  # refuse / re-enter grounding loop
