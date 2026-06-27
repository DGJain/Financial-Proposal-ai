"""Scanned-image extraction via PaddleOCR (PNG / JPG).

Lazy-imports ``paddleocr``. Each detected text region becomes an OCR ``TextBlock``
carrying its per-region confidence, so the quality stage can score OCR loss and
flag critical low-confidence regions. The whole image is treated as one scanned
page.
"""

from __future__ import annotations

from app.domain.documents.enums import FileType
from app.domain.ingestion.extracted import ExtractedDocument, ExtractedPage, TextBlock


class ImageOcrExtractor:
    """``ExtractorPort`` adapter for image sources, backed by PaddleOCR."""

    def __init__(self, lang: str = "en") -> None:
        self._lang = lang
        self._engine: object | None = None

    def supports(self, file_type: FileType) -> bool:
        return file_type in (FileType.PNG, FileType.JPG)

    def _ocr(self) -> object:
        if self._engine is None:
            from paddleocr import PaddleOCR  # lazy: heavy model

            self._engine = PaddleOCR(use_angle_cls=True, lang=self._lang, show_log=False)
        return self._engine

    async def extract(self, data: bytes, *, file_type: FileType) -> ExtractedDocument:
        import numpy as np  # lazy
        from PIL import Image  # lazy
        from io import BytesIO

        image = np.array(Image.open(BytesIO(data)).convert("RGB"))
        result = self._ocr().ocr(image, cls=True)  # type: ignore[attr-defined]

        blocks: list[TextBlock] = []
        for line in result[0] if result else []:
            (_, (text, confidence)) = line
            if text.strip():
                blocks.append(
                    TextBlock(text=text.strip(), is_ocr=True, ocr_confidence=float(confidence))
                )
        page = ExtractedPage(page_number=1, text_blocks=tuple(blocks), is_scanned=True)
        return ExtractedDocument(file_type=file_type, pages=(page,))
