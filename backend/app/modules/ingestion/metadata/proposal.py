"""Proposal layered metadata (document-intelligence U-2, proposal schema).

Derives the exemplar repository's filterable metadata: the proposal subtype, the
sections present, and the curation-supplied facts that text alone cannot reveal —
``outcome`` (won/lost, which boosts ranking toward winners), ``client`` and
``industry``. Outcome/client/industry arrive as ``hints`` from the curation gate;
subtype and sections are detected from the document.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.domain.documents.enums import ProposalSubtype
from app.domain.ingestion.extracted import ExtractedDocument
from app.domain.proposals.enums import Outcome
from app.modules.ingestion.quality.sections import ProposalSectionType, detected_sections

_SUBTYPE_MARKERS: tuple[tuple[ProposalSubtype, tuple[str, ...]], ...] = (
    (ProposalSubtype.CASE_STUDY, ("case study",)),
    (ProposalSubtype.STATEMENT_OF_WORK, ("statement of work", "sow", "scope of work")),
    (ProposalSubtype.PITCH, ("pitch", "pitch deck")),
    (ProposalSubtype.METHODOLOGY, ("methodology", "our methodology")),
    (ProposalSubtype.PAST_PROPOSAL, ("proposal", "engagement")),
)


@dataclass(frozen=True, slots=True)
class ProposalMetadata:
    """Layered metadata for a proposal exemplar."""

    subtype: ProposalSubtype
    outcome: Outcome = Outcome.PENDING
    client: str | None = None
    industry: str | None = None
    engagement_type: str | None = None
    sections_present: tuple[ProposalSectionType, ...] = ()

    @property
    def subtype_value(self) -> str:
        return self.subtype.value

    def chunk_metadata(self) -> dict[str, str | int]:
        md: dict[str, str | int] = {
            "subtype": self.subtype.value,
            "outcome": self.outcome.value,  # enables outcome=won ranking boost
        }
        if self.industry:
            md["industry"] = self.industry
        if self.engagement_type:
            md["engagement_type"] = self.engagement_type
        return md


class ProposalMetadataExtractor:
    """Extracts proposal layered metadata from a normalized document + hints."""

    def extract(
        self,
        document: ExtractedDocument,
        *,
        hints: Mapping[str, str] | None = None,
    ) -> ProposalMetadata:
        hints = hints or {}
        lowered = document.full_text.lower()
        texts = [b.text for page in document.pages for b in page.text_blocks if b.text]
        return ProposalMetadata(
            subtype=self._subtype(lowered),
            outcome=self._outcome(hints.get("outcome")),
            client=hints.get("client"),
            industry=hints.get("industry"),
            engagement_type=hints.get("engagement_type"),
            sections_present=tuple(sorted(detected_sections(texts), key=lambda s: s.value)),
        )

    def detect_subtype(self, document: ExtractedDocument) -> ProposalSubtype:
        """Public subtype detection — reused by the quality assessor (Section
        Coverage needs the subtype before full metadata extraction runs)."""
        return self._subtype(document.full_text.lower())

    def _subtype(self, lowered: str) -> ProposalSubtype:
        for subtype, markers in _SUBTYPE_MARKERS:
            if any(marker in lowered for marker in markers):
                return subtype
        return ProposalSubtype.PAST_PROPOSAL

    def _outcome(self, raw: str | None) -> Outcome:
        if not raw:
            return Outcome.PENDING
        try:
            return Outcome(raw.lower())
        except ValueError:
            return Outcome.PENDING
