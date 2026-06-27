"""Extractor port — turns raw source bytes into the layout-aware model.

The concrete adapters (PyMuPDF for PDF, python-docx/pptx for Office, an OCR-backed
extractor for scanned images) all live in ``infrastructure.extraction`` and are
selected by file type behind this one Protocol, so the ingestion use-case never
imports a document library (Clean Architecture DIP, air-gap-friendly).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain.documents.enums import FileType
from app.domain.ingestion.extracted import ExtractedDocument


@runtime_checkable
class ExtractorPort(Protocol):
    def supports(self, file_type: FileType) -> bool:
        """Whether this extractor can handle the given source format."""
        ...

    async def extract(self, data: bytes, *, file_type: FileType) -> ExtractedDocument:
        """Parse raw bytes into the normalized ``ExtractedDocument`` model."""
        ...
