"""Anonymization verification result objects (the curation leakage guard).

The proposal repository is used only for *how to say it*, never *what the numbers
are* (ARCHITECTURE_SUMMARY "Hard fact-grounding rule"). So before a curated or
approved proposal becomes an exemplar, it must be verified free of engagement-
specific content: concrete monetary figures, residual PII/MNPI, and named client
identifiers. A non-empty report is the signature of cross-engagement leakage and
blocks ingestion.

Pure value objects — the verifier service lives in ``modules.ingestion.curation``.
Findings carry a short, already-safe sample for the audit trail, never a payload
that would itself leak.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class AnonymizationFindingKind(StrEnum):
    """Category of residual sensitive content found in a candidate exemplar."""

    HARD_FIGURE = "hard_figure"  # concrete currency amount / grouped number
    RESIDUAL_PII = "residual_pii"  # an email/phone/SSN that survived redaction
    RESIDUAL_MNPI = "residual_mnpi"  # an MNPI marker that survived redaction
    CLIENT_IDENTIFIER = "client_identifier"  # a known engagement entity, verbatim


@dataclass(frozen=True, slots=True)
class AnonymizationFinding:
    kind: AnonymizationFindingKind
    sample: str  # short, safe excerpt for audit (truncated)
    page: int
    occurrences: int = 1


@dataclass(frozen=True, slots=True)
class AnonymizationReport:
    """The outcome of verifying an exemplar candidate's anonymization."""

    findings: tuple[AnonymizationFinding, ...] = field(default_factory=tuple)

    @property
    def is_clean(self) -> bool:
        return not self.findings

    def counts_by_kind(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for finding in self.findings:
            out[finding.kind.value] = out.get(finding.kind.value, 0) + finding.occurrences
        return out

    def summary(self) -> str:
        if self.is_clean:
            return "clean"
        return ", ".join(f"{k}={v}" for k, v in sorted(self.counts_by_kind().items()))
