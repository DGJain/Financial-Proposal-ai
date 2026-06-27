"""Quality & information-loss value objects (document-intelligence.md §8, U-4).

These model the *measured* quality of an extracted document: the per-modality
loss vector and the derived scores (``EQS`` and the repository-specific metrics).
The *thresholds* that turn these numbers into an approve/reject decision live in
``core.policies.quality_gates`` — measurement and policy are kept separate so the
same measurement can be re-evaluated against different gate versions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Modality(StrEnum):
    """Content modalities scored by the loss framework (``S_m = 1 − L_m``)."""

    TEXT = "text"
    OCR = "ocr"
    TABLE = "table"
    FIGURE = "figure"
    META = "meta"
    ENTITY = "entity"
    SEMANTIC_RETENTION = "semantic_retention"
    STRUCTURE = "structure"  # structure / placeholder integrity (templates)


@dataclass(frozen=True, slots=True)
class LossVector:
    """Per-modality information loss ``L_m`` in [0, 1] (0 = no loss).

    Only the modalities relevant to the document's repository need be present;
    absent modalities are treated as not-applicable by the gate.
    """

    losses: dict[Modality, float]

    def __post_init__(self) -> None:
        for modality, loss in self.losses.items():
            if not 0.0 <= loss <= 1.0:
                raise ValueError(f"loss[{modality}] must be in [0, 1] (got {loss!r})")

    def score(self, modality: Modality) -> float:
        """Modality score ``S_m = 1 − L_m`` (1.0 if modality not measured)."""
        return 1.0 - self.losses.get(modality, 0.0)


@dataclass(frozen=True, slots=True)
class QualityScores:
    """Derived quality metrics attached to an extracted document.

    A superset across repositories; only the fields relevant to a document's
    repository are populated. ``eqs`` is the weighted aggregate
    ``Σ w_m·S_m`` computed with that repository's modality weights.
    """

    eqs: float  # Extraction Quality Score (repo-weighted)
    ocr_confidence: float
    # Financial-specific
    cfr: float | None = None  # Critical Figure Retention
    rpr: float | None = None  # Reconciliation Pass Rate
    has_critical_low_confidence_region: bool = False
    # Proposal-specific
    section_coverage: float | None = None  # SC = detected / expected
    # Template-specific
    placeholder_integrity: float | None = None  # PI
    structural_fidelity: float | None = None  # SF
    # Classification soft gate
    classification_confidence: float | None = None  # conf = max(π_d)

    @property
    def information_loss_pct(self) -> float:
        """Headline information-loss % surfaced on dashboards/reports (= 1 − EQS)."""
        return round((1.0 - self.eqs) * 100.0, 2)
