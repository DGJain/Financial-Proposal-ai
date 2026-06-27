"""Repository-aware quality gate — financial predicate (document-intelligence U-4).

Turns the measured ``QualityScores`` into an APPROVE / RE_EXTRACT / HUMAN_REVIEW
verdict using the **financial** predicate from ``DEFAULT_QUALITY_GATE_POLICY``
(CFR ≥ 0.98, RPR ≥ 0.99, EQS ≥ 0.90, no critical low-confidence region). This is
the strictest of the three gates because the financial repo is the only citable
evidence — an unverified figure must never become retrievable.

Verdict routing:
* all thresholds met → **APPROVED** (proceed to index)
* numeric-integrity failure (CFR/RPR below floor, or a critical low-confidence
  region) → **HUMAN_REVIEW** (a silent re-extract could mask a wrong number)
* only EQS marginally short → **RE_EXTRACT** (recoverable by re-running extraction)
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.policies.quality_gates import (
    FinancialGatePredicate,
    ProposalGatePredicate,
    TemplateGatePredicate,
)
from app.domain.chunks.quality import QualityScores
from app.domain.generation.enums import QualityGateVerdict


@dataclass(frozen=True, slots=True)
class GateResult:
    """A gate verdict with a human-readable reason for the lineage record."""

    verdict: QualityGateVerdict
    reason: str

    @property
    def approved(self) -> bool:
        return self.verdict is QualityGateVerdict.APPROVED


@dataclass(frozen=True, slots=True)
class FinancialQualityGate:
    """Applies the financial gate predicate to measured quality scores."""

    predicate: FinancialGatePredicate

    def evaluate(self, scores: QualityScores) -> GateResult:
        cfr = scores.cfr if scores.cfr is not None else 1.0
        rpr = scores.rpr if scores.rpr is not None else 1.0

        if scores.has_critical_low_confidence_region and not self.predicate.allow_critical_low_confidence_region:
            return GateResult(
                QualityGateVerdict.HUMAN_REVIEW,
                "Critical low-confidence region detected in a numeric table.",
            )
        if cfr < self.predicate.min_cfr:
            return GateResult(
                QualityGateVerdict.HUMAN_REVIEW,
                f"CFR {cfr:.4f} below floor {self.predicate.min_cfr}.",
            )
        if rpr < self.predicate.min_rpr:
            return GateResult(
                QualityGateVerdict.HUMAN_REVIEW,
                f"RPR {rpr:.4f} below floor {self.predicate.min_rpr}.",
            )
        if scores.eqs < self.predicate.min_eqs:
            return GateResult(
                QualityGateVerdict.RE_EXTRACT,
                f"EQS {scores.eqs:.4f} below floor {self.predicate.min_eqs}.",
            )
        return GateResult(
            QualityGateVerdict.APPROVED,
            f"EQS {scores.eqs:.4f}, CFR {cfr:.4f}, RPR {rpr:.4f} — all floors met.",
        )


@dataclass(frozen=True, slots=True)
class ProposalQualityGate:
    """Applies the proposal gate predicate (EQS_prop, Section Coverage, conf).

    Optimizes narrative completeness: a sub-threshold EQS or coverage is a
    *recoverable* extraction problem (RE_EXTRACT); a confidence below θ_cls means
    the document may not be a proposal at all (HUMAN_REVIEW).
    """

    predicate: ProposalGatePredicate

    def evaluate(self, scores: QualityScores) -> GateResult:
        sc = scores.section_coverage if scores.section_coverage is not None else 1.0
        conf = scores.classification_confidence if scores.classification_confidence is not None else 1.0

        if conf < self.predicate.min_classification_confidence:
            return GateResult(
                QualityGateVerdict.HUMAN_REVIEW,
                f"classification confidence {conf:.4f} below "
                f"{self.predicate.min_classification_confidence}.",
            )
        if sc < self.predicate.min_section_coverage:
            return GateResult(
                QualityGateVerdict.RE_EXTRACT,
                f"Section coverage {sc:.4f} below {self.predicate.min_section_coverage}.",
            )
        if scores.eqs < self.predicate.min_eqs:
            return GateResult(
                QualityGateVerdict.RE_EXTRACT,
                f"EQS {scores.eqs:.4f} below {self.predicate.min_eqs}.",
            )
        return GateResult(
            QualityGateVerdict.APPROVED,
            f"EQS {scores.eqs:.4f}, SC {sc:.4f}, conf {conf:.4f} — all floors met.",
        )


@dataclass(frozen=True, slots=True)
class TemplateQualityGate:
    """Applies the template gate predicate (Placeholder Integrity, Structural
    Fidelity, EQS_tmpl).

    Optimizes structural/placeholder integrity: a malformed slot is not silently
    recoverable (a wrong placeholder breaks downstream fill), so PI/SF failures go
    to HUMAN_REVIEW; only a marginal EQS short-fall is RE_EXTRACT.
    """

    predicate: TemplateGatePredicate

    def evaluate(self, scores: QualityScores) -> GateResult:
        pi = scores.placeholder_integrity if scores.placeholder_integrity is not None else 1.0
        sf = scores.structural_fidelity if scores.structural_fidelity is not None else 1.0

        if pi < self.predicate.min_placeholder_integrity:
            return GateResult(
                QualityGateVerdict.HUMAN_REVIEW,
                f"Placeholder integrity {pi:.4f} below "
                f"{self.predicate.min_placeholder_integrity}.",
            )
        if sf < self.predicate.min_structural_fidelity:
            return GateResult(
                QualityGateVerdict.HUMAN_REVIEW,
                f"Structural fidelity {sf:.4f} below {self.predicate.min_structural_fidelity}.",
            )
        if scores.eqs < self.predicate.min_eqs:
            return GateResult(
                QualityGateVerdict.RE_EXTRACT,
                f"EQS {scores.eqs:.4f} below {self.predicate.min_eqs}.",
            )
        return GateResult(
            QualityGateVerdict.APPROVED,
            f"EQS {scores.eqs:.4f}, PI {pi:.4f}, SF {sf:.4f} — all floors met.",
        )
