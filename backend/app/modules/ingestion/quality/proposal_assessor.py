"""Proposal quality assessment — EQS_prop + Section Coverage (document-intelligence
U-4).

The proposal repository is the *exemplar* corpus: it is judged on narrative
completeness, not numeric integrity. So the assessor weights text/semantic
retention (via ``PROPOSAL_WEIGHTS``) and computes **Section Coverage**
``SC = sections_detected / sections_expected(subtype)`` — the share of the
sections a proposal of this subtype is expected to contain.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.chunks.quality import LossVector, Modality, QualityScores
from app.domain.ingestion.extracted import ExtractedDocument
from app.domain.documents.enums import ProposalSubtype
from app.modules.ingestion.quality.sections import detected_sections, expected_sections


@dataclass(frozen=True, slots=True)
class ProposalQualityAssessor:
    """Computes EQS_prop and Section Coverage for a proposal exemplar."""

    weights: dict[Modality, float]

    def assess(self, document: ExtractedDocument, *, subtype: ProposalSubtype) -> QualityScores:
        ocr_confidence = document.mean_ocr_confidence
        section_coverage = self._section_coverage(document, subtype)

        losses = {
            Modality.TEXT: self._text_loss(document),
            Modality.OCR: 1.0 - ocr_confidence,
            Modality.TABLE: 0.0,
            Modality.FIGURE: self._figure_loss(document),
            Modality.META: 0.0,
            Modality.ENTITY: 0.0,
            # Narrative meaning is taken as retained when the expected sections are
            # present; missing sections are the dominant proposal-quality signal.
            Modality.SEMANTIC_RETENTION: 1.0 - section_coverage,
        }
        loss_vector = LossVector(losses=losses)
        eqs = sum(weight * loss_vector.score(modality) for modality, weight in self.weights.items())

        return QualityScores(
            eqs=round(eqs, 6),
            ocr_confidence=round(ocr_confidence, 6),
            section_coverage=round(section_coverage, 6),
        )

    def _section_coverage(self, document: ExtractedDocument, subtype: ProposalSubtype) -> float:
        expected = expected_sections(subtype)
        if not expected:
            return 1.0
        texts = [b.text for page in document.pages for b in page.text_blocks if b.text]
        found = detected_sections(texts) & expected
        return len(found) / len(expected)

    def _text_loss(self, document: ExtractedDocument) -> float:
        ocr_blocks = [
            b
            for page in document.pages
            for b in page.text_blocks
            if b.is_ocr and b.ocr_confidence is not None
        ]
        if not ocr_blocks:
            return 0.0
        mean_conf = sum(b.ocr_confidence for b in ocr_blocks) / len(ocr_blocks)  # type: ignore[misc]
        return 1.0 - mean_conf

    def _figure_loss(self, document: ExtractedDocument) -> float:
        figures = [fig for _, fig in document.figures()]
        if not figures:
            return 0.0
        at_risk = sum(1 for fig in figures if fig.ocr_confidence is not None and fig.ocr_confidence < 0.85)
        return at_risk / len(figures)
