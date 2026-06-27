"""Composite extractor — dispatches a source to the adapter that supports it.

Presents one ``ExtractorPort`` to the ingestion use-case while routing by file
type to the PDF, Office, or image-OCR adapter underneath. Each underlying adapter
lazy-imports its library, so constructing the composite is cheap and air-gap-safe.
"""

from __future__ import annotations

from app.domain.documents.enums import FileType
from app.domain.ingestion.extracted import ExtractedDocument
from app.domain.ports.extractor import ExtractorPort
from app.infrastructure.extraction.image_extractor import ImageOcrExtractor
from app.infrastructure.extraction.office_extractor import OfficeExtractor
from app.infrastructure.extraction.pymupdf_extractor import PyMuPdfExtractor


class CompositeExtractor:
    """Routes by ``FileType`` to a per-format ``ExtractorPort`` adapter."""

    def __init__(self, extractors: tuple[ExtractorPort, ...] | None = None) -> None:
        self._extractors: tuple[ExtractorPort, ...] = extractors or (
            PyMuPdfExtractor(),
            OfficeExtractor(),
            ImageOcrExtractor(),
        )

    def supports(self, file_type: FileType) -> bool:
        return any(e.supports(file_type) for e in self._extractors)

    async def extract(self, data: bytes, *, file_type: FileType) -> ExtractedDocument:
        for extractor in self._extractors:
            if extractor.supports(file_type):
                return await extractor.extract(data, file_type=file_type)
        raise ValueError(f"No extractor supports file type {file_type!r}")
