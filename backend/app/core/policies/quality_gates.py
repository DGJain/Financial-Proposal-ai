"""Repository-aware quality-gate policy.

Centralizes the loss-framework knobs from document-intelligence.md (U-4):
modality weight vectors for ``EQS = Σ w_m·S_m`` and the per-repository gate
predicates. These are research parameters — keeping them in one immutable,
versioned place makes every gate decision reproducible and lets the exact
weights/thresholds be recorded alongside each ingestion in the audit lineage.

Notation: ``S_m = 1 − L_m`` (modality score = 1 − modality loss);
``EQS = Σ_m w_m · S_m``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.chunks.quality import Modality

# --- Modality weight vectors (document-intelligence.md U-4) -------------------
# Each vector sums to 1.0 across the modalities that apply to that repository.

FINANCIAL_WEIGHTS: dict[Modality, float] = {
    Modality.TEXT: 0.20,
    Modality.OCR: 0.10,
    Modality.TABLE: 0.30,  # tables carry the figures — weighted heaviest
    Modality.FIGURE: 0.05,
    Modality.META: 0.05,
    Modality.ENTITY: 0.30,  # entity/figure retention is critical for finance
}

PROPOSAL_WEIGHTS: dict[Modality, float] = {
    Modality.TEXT: 0.40,
    Modality.OCR: 0.05,
    Modality.TABLE: 0.10,
    Modality.FIGURE: 0.05,
    Modality.META: 0.10,
    Modality.ENTITY: 0.10,
    Modality.SEMANTIC_RETENTION: 0.20,  # narrative meaning matters most
}

TEMPLATE_WEIGHTS: dict[Modality, float] = {
    Modality.TEXT: 0.15,
    Modality.OCR: 0.05,
    Modality.TABLE: 0.05,
    Modality.META: 0.10,
    Modality.STRUCTURE: 0.65,  # placeholder/structural integrity dominates
}


@dataclass(frozen=True, slots=True)
class FinancialGatePredicate:
    """Approve iff CFR ≥ min_cfr AND RPR ≥ min_rpr AND EQS_fin ≥ min_eqs
    AND no critical low-confidence region. Strictest bar (numeric integrity)."""

    min_cfr: float = 0.98  # Critical Figure Retention
    min_rpr: float = 0.99  # Reconciliation Pass Rate
    min_eqs: float = 0.90
    allow_critical_low_confidence_region: bool = False


@dataclass(frozen=True, slots=True)
class ProposalGatePredicate:
    """Approve iff EQS_prop ≥ min_eqs AND SC ≥ min_section_coverage
    AND conf ≥ theta_cls. Optimizes narrative completeness."""

    min_eqs: float = 0.85
    min_section_coverage: float = 0.90  # SC = sections_detected / sections_expected
    min_classification_confidence: float = 0.70  # tied to ClassifierPolicy.theta_cls


@dataclass(frozen=True, slots=True)
class TemplateGatePredicate:
    """Approve iff PI ≥ min_placeholder_integrity AND SF ≥ min_structural_fidelity
    AND EQS_tmpl ≥ min_eqs. Optimizes structural/placeholder integrity."""

    min_placeholder_integrity: float = 0.99  # PI = placeholders_wellformed / total
    min_structural_fidelity: float = 0.95  # SF = elements_preserved / source
    min_eqs: float = 0.90


@dataclass(frozen=True, slots=True)
class QualityGatePolicy:
    """Bundle of modality weights + per-repository gate predicates."""

    financial_weights: dict[Modality, float] = field(
        default_factory=lambda: dict(FINANCIAL_WEIGHTS)
    )
    proposal_weights: dict[Modality, float] = field(
        default_factory=lambda: dict(PROPOSAL_WEIGHTS)
    )
    template_weights: dict[Modality, float] = field(
        default_factory=lambda: dict(TEMPLATE_WEIGHTS)
    )
    financial_gate: FinancialGatePredicate = field(default_factory=FinancialGatePredicate)
    proposal_gate: ProposalGatePredicate = field(default_factory=ProposalGatePredicate)
    template_gate: TemplateGatePredicate = field(default_factory=TemplateGatePredicate)


DEFAULT_QUALITY_GATE_POLICY = QualityGatePolicy()
