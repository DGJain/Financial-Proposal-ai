"""Financial quality assessment — the measured loss vector + derived scores.

Implements the financial slice of the loss framework (document-intelligence.md
§8/U-4). It turns an ``ExtractedDocument`` into a per-modality ``LossVector`` and
the financial ``QualityScores`` (EQS, OCR confidence, CFR, RPR), which the gate
then judges. Measurement only — thresholds live in ``core.policies.quality_gates``
so the same numbers can be re-judged against a different policy version.

Financial-specific metrics:
* **CFR** (Critical Figure Retention) — share of numeric table cells extracted
  with adequate confidence (low-confidence numeric content is "at risk").
* **RPR** (Reconciliation Pass Rate) — share of total-bearing tables whose stated
  total reconciles with the sum of its column.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.chunks.quality import LossVector, Modality, QualityScores
from app.domain.ingestion.extracted import ExtractedDocument, ExtractedTable

_NUMERIC = re.compile(r"-?\(?\$?\s*\d[\d,]*(?:\.\d+)?\)?")

# A numeric region below this OCR confidence is treated as a critical risk.
CRITICAL_CONFIDENCE_FLOOR = 0.85
# Tolerance (relative) for a reconciliation total to count as passing.
RECONCILIATION_TOLERANCE = 0.01


def _parse_number(cell: str) -> float | None:
    text = cell.strip()
    if not _NUMERIC.fullmatch(text):
        return None
    negative = text.startswith("(") and text.endswith(")")
    cleaned = text.strip("()").replace("$", "").replace(",", "").strip()
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return -value if negative else value


@dataclass(frozen=True, slots=True)
class FinancialQualityAssessor:
    """Computes the financial ``LossVector`` and ``QualityScores`` for a document."""

    weights: dict[Modality, float]

    def assess(self, document: ExtractedDocument) -> QualityScores:
        ocr_confidence = document.mean_ocr_confidence
        cfr, has_low_conf_region = self._critical_figure_retention(document)
        rpr = self._reconciliation_pass_rate(document)

        losses = {
            Modality.TEXT: self._text_loss(document),
            Modality.OCR: 1.0 - ocr_confidence,
            Modality.TABLE: 1.0 - cfr,
            Modality.FIGURE: self._figure_loss(document),
            Modality.META: 0.0,
            Modality.ENTITY: 1.0 - cfr,  # entity/figure integrity tracks CFR
        }
        loss_vector = LossVector(losses=losses)
        eqs = sum(weight * loss_vector.score(modality) for modality, weight in self.weights.items())

        return QualityScores(
            eqs=round(eqs, 6),
            ocr_confidence=round(ocr_confidence, 6),
            cfr=round(cfr, 6),
            rpr=round(rpr, 6),
            has_critical_low_confidence_region=has_low_conf_region,
        )

    # --- per-modality helpers ------------------------------------------------

    def _text_loss(self, document: ExtractedDocument) -> float:
        ocr_blocks = [
            b
            for page in document.pages
            for b in page.text_blocks
            if b.is_ocr and b.ocr_confidence is not None
        ]
        if not ocr_blocks:
            return 0.0  # born-digital text is taken as lossless
        mean_conf = sum(b.ocr_confidence for b in ocr_blocks) / len(ocr_blocks)  # type: ignore[misc]
        return 1.0 - mean_conf

    def _figure_loss(self, document: ExtractedDocument) -> float:
        figures = [fig for _, fig in document.figures()]
        if not figures:
            return 0.0
        at_risk = sum(
            1 for fig in figures if fig.ocr_confidence is not None and fig.ocr_confidence < CRITICAL_CONFIDENCE_FLOOR
        )
        return at_risk / len(figures)

    def _critical_figure_retention(self, document: ExtractedDocument) -> tuple[float, bool]:
        total_numeric = 0
        retained = 0
        has_low_conf_region = False
        for _, table in document.tables():
            confidence = table.ocr_confidence
            table_low_conf = confidence is not None and confidence < CRITICAL_CONFIDENCE_FLOOR
            for row in table.rows:
                for cell in row:
                    if _parse_number(cell) is None:
                        continue
                    total_numeric += 1
                    if table_low_conf:
                        has_low_conf_region = True
                    else:
                        retained += 1
        if total_numeric == 0:
            return 1.0, has_low_conf_region
        return retained / total_numeric, has_low_conf_region

    def _reconciliation_pass_rate(self, document: ExtractedDocument) -> float:
        checkable = 0
        passing = 0
        for _, table in document.tables():
            if not table.has_total_row or len(table.rows) < 2:
                continue
            result = self._reconciles(table)
            if result is None:
                continue
            checkable += 1
            if result:
                passing += 1
        return passing / checkable if checkable else 1.0

    def _reconciles(self, table: ExtractedTable) -> bool | None:
        """Whether the final row's total equals the sum of the column above it."""
        *body, total_row = table.rows
        # Find the rightmost column that is numeric in the total row.
        for col in range(len(total_row) - 1, -1, -1):
            stated = _parse_number(total_row[col])
            if stated is None:
                continue
            components = [
                value
                for row in body
                if col < len(row) and (value := _parse_number(row[col])) is not None
            ]
            if not components:
                return None
            summed = sum(components)
            if abs(stated) < 1e-9:
                return abs(summed) < 1e-9
            return abs(summed - stated) <= abs(stated) * RECONCILIATION_TOLERANCE
        return None
