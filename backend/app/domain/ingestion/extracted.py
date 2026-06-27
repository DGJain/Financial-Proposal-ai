"""Normalized extraction model — the layout-aware intermediate of the pipeline.

Extractors (PyMuPDF / Docling / python-docx / python-pptx / OCR) all converge on
this single shape (document-intelligence.md U-1): a document is a sequence of
pages, each carrying flowing ``TextBlock``s, atomic ``ExtractedTable``s, and
``ExtractedFigure``s, every region optionally annotated with an OCR confidence so
the quality stage can score per-modality information loss.

Pure value objects: no I/O, no library types leak in. The heavy library handling
lives behind ``ExtractorPort`` adapters; they emit only these dataclasses.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

from app.domain.documents.enums import FileType

BBox = tuple[float, float, float, float]  # x0, y0, x1, y1


@dataclass(frozen=True, slots=True)
class TextBlock:
    """A contiguous run of flowing text on one page."""

    text: str
    bbox: BBox | None = None
    is_ocr: bool = False
    ocr_confidence: float | None = None  # [0, 1] when produced by OCR


@dataclass(frozen=True, slots=True)
class ExtractedTable:
    """A table extracted atomically — rows preserved, never split across chunks."""

    table_id: str
    rows: tuple[tuple[str, ...], ...]
    caption: str | None = None
    bbox: BBox | None = None
    ocr_confidence: float | None = None
    has_total_row: bool = False  # hint for reconciliation checks

    def render(self) -> str:
        """Flatten to a deterministic text serialization for embedding."""
        lines = [" | ".join(cell for cell in row) for row in self.rows]
        body = "\n".join(lines)
        return f"{self.caption}\n{body}" if self.caption else body


@dataclass(frozen=True, slots=True)
class ExtractedFigure:
    """A figure/chart kept together with its caption."""

    figure_id: str
    caption: str | None = None
    bbox: BBox | None = None
    ocr_confidence: float | None = None


@dataclass(frozen=True, slots=True)
class ExtractedPage:
    """One source page with its layout-segmented regions."""

    page_number: int  # 1-based
    text_blocks: tuple[TextBlock, ...] = ()
    tables: tuple[ExtractedTable, ...] = ()
    figures: tuple[ExtractedFigure, ...] = ()
    is_scanned: bool = False  # image-only page that required OCR

    @property
    def text(self) -> str:
        return "\n".join(b.text for b in self.text_blocks if b.text)


@dataclass(frozen=True, slots=True)
class ExtractedDocument:
    """A whole source rendered into the pipeline's layout-aware model."""

    file_type: FileType
    pages: tuple[ExtractedPage, ...]
    language: str = "en"
    metadata: dict[str, str] = field(default_factory=dict)  # raw container metadata

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def full_text(self) -> str:
        return "\n\n".join(p.text for p in self.pages if p.text)

    def tables(self) -> Iterator[tuple[int, ExtractedTable]]:
        """Yield ``(page_number, table)`` across the document."""
        for page in self.pages:
            for table in page.tables:
                yield page.page_number, table

    def figures(self) -> Iterator[tuple[int, ExtractedFigure]]:
        for page in self.pages:
            for figure in page.figures:
                yield page.page_number, figure

    def ocr_confidences(self) -> list[float]:
        """Every per-region OCR confidence present in the document."""
        out: list[float] = []
        for page in self.pages:
            out.extend(b.ocr_confidence for b in page.text_blocks if b.ocr_confidence is not None)
            out.extend(t.ocr_confidence for t in page.tables if t.ocr_confidence is not None)
            out.extend(f.ocr_confidence for f in page.figures if f.ocr_confidence is not None)
        return out

    @property
    def mean_ocr_confidence(self) -> float:
        """Mean OCR confidence; 1.0 when nothing required OCR (born-digital)."""
        confidences = self.ocr_confidences()
        return sum(confidences) / len(confidences) if confidences else 1.0
