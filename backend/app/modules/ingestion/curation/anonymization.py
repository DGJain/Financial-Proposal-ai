"""Anonymization verifier — the curation gate's leakage check for exemplars.

Runs on the *normalized* (already PII/MNPI-redacted) document and looks for what
redaction deliberately leaves but an exemplar must not carry: concrete monetary
figures and grouped numbers (the "what the numbers are"), any residual PII/MNPI
that slipped through, and verbatim occurrences of known engagement identifiers
(client/counterparty names supplied by the caller). Any finding blocks ingestion
into ``repo_proposals`` — this is the enforcement point for the hard
fact-grounding rule (ARCHITECTURE_SUMMARY) at curation time.

Deterministic and dependency-free (regex + literal matching), so it behaves
identically in the air-gapped cluster and in tests.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.ingestion.anonymization import (
    AnonymizationFinding,
    AnonymizationFindingKind,
    AnonymizationReport,
)
from app.domain.ingestion.extracted import ExtractedDocument

# Concrete currency amount: a currency mark followed by digits (placeholders like
# "$X" or "$[AMOUNT]" do not match because the char after the mark is not a digit).
_CURRENCY = re.compile(r"[$£€]\s?\d[\d,]*(?:\.\d+)?\s?(?:bn|mn|m|k|million|billion)?", re.IGNORECASE)
# A grouped number (thousands separators) — a hard figure even without a currency mark.
_GROUPED_NUMBER = re.compile(r"\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_MNPI = re.compile(r"\bMNPI\b|MATERIAL NON-?PUBLIC", re.IGNORECASE)

_SAMPLE_LEN = 24


def _truncate(text: str) -> str:
    text = text.strip()
    return text if len(text) <= _SAMPLE_LEN else text[: _SAMPLE_LEN - 1] + "…"


@dataclass(frozen=True, slots=True)
class AnonymizationVerifier:
    """Verifies a candidate exemplar carries no engagement-specific content."""

    def verify(
        self,
        document: ExtractedDocument,
        *,
        known_identifiers: frozenset[str] = frozenset(),
    ) -> AnonymizationReport:
        findings: list[AnonymizationFinding] = []
        findings.extend(self._scan(document, AnonymizationFindingKind.HARD_FIGURE, _CURRENCY))
        findings.extend(self._scan(document, AnonymizationFindingKind.HARD_FIGURE, _GROUPED_NUMBER))
        findings.extend(self._scan(document, AnonymizationFindingKind.RESIDUAL_PII, _EMAIL))
        findings.extend(self._scan(document, AnonymizationFindingKind.RESIDUAL_MNPI, _MNPI))
        findings.extend(self._scan_identifiers(document, known_identifiers))
        return AnonymizationReport(findings=tuple(findings))

    def _scan(
        self,
        document: ExtractedDocument,
        kind: AnonymizationFindingKind,
        pattern: re.Pattern[str],
    ) -> list[AnonymizationFinding]:
        occurrences = 0
        first: tuple[str, int] | None = None
        for page in document.pages:
            for block in page.text_blocks:
                for match in pattern.finditer(block.text):
                    occurrences += 1
                    if first is None:
                        first = (match.group(0), page.page_number)
        if first is None:
            return []
        sample, page_no = first
        return [AnonymizationFinding(kind=kind, sample=_truncate(sample), page=page_no, occurrences=occurrences)]

    def _scan_identifiers(
        self, document: ExtractedDocument, known_identifiers: frozenset[str]
    ) -> list[AnonymizationFinding]:
        findings: list[AnonymizationFinding] = []
        for identifier in known_identifiers:
            needle = identifier.strip().lower()
            if not needle:
                continue
            occurrences = 0
            page_no = 0
            for page in document.pages:
                for block in page.text_blocks:
                    hits = block.text.lower().count(needle)
                    if hits and page_no == 0:
                        page_no = page.page_number
                    occurrences += hits
            if occurrences:
                findings.append(
                    AnonymizationFinding(
                        kind=AnonymizationFindingKind.CLIENT_IDENTIFIER,
                        sample=_truncate(identifier),
                        page=page_no,
                        occurrences=occurrences,
                    )
                )
        return findings
