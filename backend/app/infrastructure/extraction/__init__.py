"""Extraction adapters — raw bytes → the layout-aware ``ExtractedDocument``.

Each adapter implements ``ExtractorPort`` for one family of formats and
lazy-imports its document library so importing this package stays light and
air-gap-safe. ``CompositeExtractor`` is the one bound at the composition root.
"""

from app.infrastructure.extraction.composite import CompositeExtractor
from app.infrastructure.extraction.image_extractor import ImageOcrExtractor
from app.infrastructure.extraction.office_extractor import OfficeExtractor
from app.infrastructure.extraction.pymupdf_extractor import PyMuPdfExtractor

__all__ = [
    "CompositeExtractor",
    "ImageOcrExtractor",
    "OfficeExtractor",
    "PyMuPdfExtractor",
]
