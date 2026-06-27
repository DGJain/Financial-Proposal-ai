"""Normalization + PII/MNPI redaction (document-intelligence.md U-2).

Cleans extracted text and removes sensitive spans **before** anything is embedded
or persisted, recording every removal in a :class:`RedactionLedger`. Two hard
rules shape the logic:

* Redaction is **not** information loss — placeholders preserve span structure and
  the ledger is kept separate from the quality/EQS path.
* Financial **figures are never redacted** — they must survive for Critical Figure
  Retention. Only PII (emails, phones, SSNs) and explicit MNPI markers are removed.

Pure and deterministic (regex only): no model, no I/O — so it runs identically in
the air-gapped cluster and in tests.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from app.domain.ingestion.extracted import (
    ExtractedDocument,
    ExtractedPage,
    TextBlock,
)
from app.domain.ingestion.redaction import (
    NormalizedDocument,
    RedactionEntry,
    RedactionKind,
    RedactionLedger,
)

# (pattern_name, kind, compiled regex). Order matters: longer/structured patterns
# first so e.g. an SSN is not partially matched as a phone fragment.
_PATTERNS: tuple[tuple[str, RedactionKind, re.Pattern[str]], ...] = (
    ("email", RedactionKind.PII, re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("ssn", RedactionKind.PII, re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("phone", RedactionKind.PII, re.compile(r"\b\+?\d{1,2}[\s.-]?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b")),
    # Explicit material non-public information markers placed by source controls.
    ("mnpi_marker", RedactionKind.MNPI, re.compile(r"\bMNPI\b|\bMATERIAL NON[- ]PUBLIC\b", re.IGNORECASE)),
)

_WHITESPACE = re.compile(r"[ \t]+")


def _placeholder(kind: RedactionKind) -> str:
    return f"[REDACTED:{kind.value.upper()}]"


class Redactor:
    """Cleans whitespace and redacts PII/MNPI, emitting a redaction ledger."""

    def normalize(self, document: ExtractedDocument) -> NormalizedDocument:
        entries: list[RedactionEntry] = []
        pages: list[ExtractedPage] = []
        for page in document.pages:
            blocks = tuple(
                self._redact_block(block, page.page_number, entries)
                for block in page.text_blocks
            )
            # Tables/figures keep their figures intact; only their captions are
            # cleaned for whitespace (no redaction of numeric content).
            pages.append(
                ExtractedPage(
                    page_number=page.page_number,
                    text_blocks=blocks,
                    tables=page.tables,
                    figures=page.figures,
                    is_scanned=page.is_scanned,
                )
            )
        normalized_doc = ExtractedDocument(
            file_type=document.file_type,
            pages=tuple(pages),
            language=document.language,
            metadata=dict(document.metadata),
        )
        return NormalizedDocument(
            document=normalized_doc,
            redaction=RedactionLedger(entries=tuple(entries)),
        )

    def _redact_block(
        self, block: TextBlock, page: int, sink: list[RedactionEntry]
    ) -> TextBlock:
        cleaned = _WHITESPACE.sub(" ", block.text).strip()
        redacted, new_entries = self._apply_patterns(cleaned, page)
        sink.extend(new_entries)
        return TextBlock(
            text=redacted,
            bbox=block.bbox,
            is_ocr=block.is_ocr,
            ocr_confidence=block.ocr_confidence,
        )

    def _apply_patterns(
        self, text: str, page: int
    ) -> tuple[str, list[RedactionEntry]]:
        entries: list[RedactionEntry] = []

        def _matches() -> Iterator[tuple[str, RedactionKind, re.Match[str]]]:
            for name, kind, pattern in _PATTERNS:
                for match in pattern.finditer(text):
                    yield name, kind, match

        # Collect, then rebuild left-to-right so spans stay coherent after splice.
        found = sorted(_matches(), key=lambda t: t[2].start())
        if not found:
            return text, entries
        out: list[str] = []
        cursor = 0
        for name, kind, match in found:
            if match.start() < cursor:
                continue  # overlapping match already redacted
            placeholder = _placeholder(kind)
            out.append(text[cursor : match.start()])
            out.append(placeholder)
            entries.append(
                RedactionEntry(
                    kind=kind,
                    pattern_name=name,
                    page=page,
                    span_start=match.start(),
                    span_end=match.end(),
                    placeholder=placeholder,
                )
            )
            cursor = match.end()
        out.append(text[cursor:])
        return "".join(out), entries
