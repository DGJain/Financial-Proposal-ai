"""PDF extraction via PyMuPDF (``fitz``).

Lazy-imports ``fitz`` inside ``extract`` so importing this module touches no heavy
(or air-gap-restricted) dependency — the composition root can wire it
unconditionally and it only loads PyMuPDF when a PDF is actually ingested. Emits
the shared ``ExtractedDocument`` model: per-page text blocks plus any tables
PyMuPDF detects, with a ``is_scanned`` flag for image-only pages (which the OCR
path handles).
"""

from __future__ import annotations

from app.domain.documents.enums import FileType
from app.domain.ingestion.extracted import (
    ExtractedDocument,
    ExtractedPage,
    ExtractedTable,
    TextBlock,
)


class PyMuPdfExtractor:
    """``ExtractorPort`` adapter for PDF sources."""

    def supports(self, file_type: FileType) -> bool:
        return file_type is FileType.PDF

    async def extract(self, data: bytes, *, file_type: FileType) -> ExtractedDocument:
        import fitz  # lazy: heavy, air-gapped wheel

        pages: list[ExtractedPage] = []
        with fitz.open(stream=data, filetype="pdf") as doc:
            for index, page in enumerate(doc, start=1):
                raw_text = page.get_text("text").strip()
                blocks = (TextBlock(text=raw_text),) if raw_text else ()
                tables = self._extract_tables(page, index)
                pages.append(
                    ExtractedPage(
                        page_number=index,
                        text_blocks=blocks,
                        tables=tables,
                        is_scanned=not raw_text,
                    )
                )
        return ExtractedDocument(file_type=FileType.PDF, pages=tuple(pages))

    @staticmethod
    def _extract_tables(page: object, page_no: int) -> tuple[ExtractedTable, ...]:
        finder = getattr(page, "find_tables", None)
        if finder is None:
            return ()
        out: list[ExtractedTable] = []
        for t_index, table in enumerate(finder().tables):
            rows = tuple(
                tuple((cell or "").strip() for cell in row) for row in table.extract()
            )
            if rows:
                out.append(
                    ExtractedTable(
                        table_id=f"p{page_no}-t{t_index}",
                        rows=rows,
                        has_total_row=_looks_like_total(rows[-1]),
                    )
                )
        return tuple(out)


def _looks_like_total(row: tuple[str, ...]) -> bool:
    joined = " ".join(row).lower()
    return any(marker in joined for marker in ("total", "net", "sum"))
