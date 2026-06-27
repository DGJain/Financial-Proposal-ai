"""Template quality assessment — EQS_tmpl + Placeholder Integrity + Structural
Fidelity (document-intelligence U-4).

The template repository is the *scaffold* corpus: text content matters least,
structural and placeholder integrity matter most (``TEMPLATE_WEIGHTS`` puts 0.65
on structure). The assessor computes:

* **PI** — ``placeholders_wellformed / placeholders_total``; and
* **SF** — ``structural_elements_preserved / structural_elements_source``,
  approximated at ingestion as the share of structural units (text blocks, tables,
  slots) that survived extraction well-formed.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.chunks.quality import LossVector, Modality, QualityScores
from app.domain.ingestion.extracted import ExtractedDocument
from app.modules.ingestion.quality.placeholders import (
    find_slots,
    placeholder_integrity,
)


@dataclass(frozen=True, slots=True)
class TemplateQualityAssessor:
    """Computes EQS_tmpl, Placeholder Integrity and Structural Fidelity."""

    weights: dict[Modality, float]

    def assess(self, document: ExtractedDocument) -> QualityScores:
        ocr_confidence = document.mean_ocr_confidence
        slots = [slot for page in document.pages for b in page.text_blocks for slot in find_slots(b.text)]
        pi = placeholder_integrity(slots)
        sf = self._structural_fidelity(document, slots)

        losses = {
            Modality.TEXT: self._text_loss(document),
            Modality.OCR: 1.0 - ocr_confidence,
            Modality.TABLE: 0.0,
            Modality.META: 0.0,
            Modality.STRUCTURE: 1.0 - pi,  # placeholder integrity dominates structure
        }
        loss_vector = LossVector(losses=losses)
        eqs = sum(weight * loss_vector.score(modality) for modality, weight in self.weights.items())

        return QualityScores(
            eqs=round(eqs, 6),
            ocr_confidence=round(ocr_confidence, 6),
            placeholder_integrity=round(pi, 6),
            structural_fidelity=round(sf, 6),
        )

    def _structural_fidelity(self, document: ExtractedDocument, slots: list) -> float:  # type: ignore[type-arg]
        blocks = [b for page in document.pages for b in page.text_blocks]
        tables = [t for _, t in document.tables()]
        total = len(blocks) + len(tables) + len(slots)
        if total == 0:
            return 1.0
        preserved = (
            sum(1 for b in blocks if b.text.strip())
            + len(tables)
            + sum(1 for s in slots if s.well_formed)
        )
        return preserved / total

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
