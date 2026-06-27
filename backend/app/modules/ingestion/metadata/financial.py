"""Financial layered metadata (document-intelligence.md U-2).

Derives the financial repository's filterable metadata from the normalized
document: the issuer, the fiscal period, identifiers (ticker/CIK), a
``critical_figures_index`` (the headline numbers with their page), a table
inventory, and the document ``subtype``. This metadata is stamped onto the
document catalog row and copied onto each chunk so retrieval can filter by e.g.
``fiscal_year`` without re-reading the source (rag-design.md within-repo filters).

Heuristic + deterministic (regex); the production extractor can enrich this
behind the same shape.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from app.domain.documents.enums import FinancialSubtype
from app.domain.ingestion.extracted import ExtractedDocument

_FISCAL_YEAR = re.compile(r"\b(?:FY\s?|fiscal year\s+|year ended.*?)(20\d{2}|19\d{2})\b", re.IGNORECASE)
_BARE_YEAR = re.compile(r"\b(20\d{2})\b")
_TICKER = re.compile(r"\((?:NYSE|NASDAQ|LSE):\s?([A-Z]{1,5})\)")
_CIK = re.compile(r"\bCIK[:\s#]*?(\d{4,10})\b", re.IGNORECASE)
_CRITICAL_LABELS = (
    "total revenue", "revenue", "net income", "net loss", "total assets",
    "total liabilities", "ebitda", "operating income", "gross profit",
    "cash and cash equivalents", "total equity",
)
_FIGURE_VALUE = re.compile(r"[-(]?\$?\s*\d[\d,]*(?:\.\d+)?\)?")

# Subtype detection keywords, most-specific first.
_SUBTYPE_MARKERS: tuple[tuple[FinancialSubtype, tuple[str, ...]], ...] = (
    (FinancialSubtype.REGULATORY_FILING, ("form 10-k", "form 10-q", "8-k", "sec filing")),
    (FinancialSubtype.ANNUAL_REPORT, ("annual report",)),
    (FinancialSubtype.PROSPECTUS, ("prospectus",)),
    (FinancialSubtype.TERM_SHEET, ("term sheet",)),
    (FinancialSubtype.CREDIT_MEMO, ("credit memo",)),
    (FinancialSubtype.INVESTMENT_REPORT, ("investment report", "portfolio review")),
    (FinancialSubtype.RESEARCH, ("research note", "equity research", "analyst report")),
    (FinancialSubtype.FINANCIAL_STATEMENT, ("balance sheet", "income statement", "cash flow statement")),
)


@dataclass(frozen=True, slots=True)
class CriticalFigure:
    label: str
    value: str
    page: int


@dataclass(frozen=True, slots=True)
class TableInventoryEntry:
    table_id: str
    page: int
    n_rows: int
    n_cols: int
    statement_type: str | None


@dataclass(frozen=True, slots=True)
class FinancialMetadata:
    """Layered financial metadata for a document."""

    subtype: FinancialSubtype
    issuer: str | None = None
    fiscal_year: int | None = None
    identifiers: dict[str, str] = field(default_factory=dict)
    critical_figures_index: tuple[CriticalFigure, ...] = ()
    table_inventory: tuple[TableInventoryEntry, ...] = ()

    @property
    def subtype_value(self) -> str:
        return self.subtype.value

    def chunk_metadata(self) -> dict[str, str | int]:
        """The subset stamped onto every chunk as filterable ChromaDB metadata."""
        md: dict[str, str | int] = {"subtype": self.subtype.value}
        if self.fiscal_year is not None:
            md["fiscal_year"] = self.fiscal_year
        if self.issuer:
            md["issuer"] = self.issuer
        return md


class FinancialMetadataExtractor:
    """Extracts financial layered metadata from a normalized document."""

    def extract(
        self,
        document: ExtractedDocument,
        *,
        hints: Mapping[str, str] | None = None,
    ) -> FinancialMetadata:
        text = document.full_text
        lowered = text.lower()
        return FinancialMetadata(
            subtype=self._subtype(lowered),
            issuer=self._issuer(document),
            fiscal_year=self._fiscal_year(text),
            identifiers=self._identifiers(text),
            critical_figures_index=self._critical_figures(document),
            table_inventory=self._table_inventory(document),
        )

    def _subtype(self, lowered: str) -> FinancialSubtype:
        for subtype, markers in _SUBTYPE_MARKERS:
            if any(marker in lowered for marker in markers):
                return subtype
        return FinancialSubtype.USER_UPLOAD

    def _issuer(self, document: ExtractedDocument) -> str | None:
        # Heuristic: the first non-empty text line of the first page.
        for page in document.pages:
            for block in page.text_blocks:
                line = block.text.strip().splitlines()[0] if block.text.strip() else ""
                if 2 <= len(line) <= 80:
                    return line
        return None

    def _fiscal_year(self, text: str) -> int | None:
        match = _FISCAL_YEAR.search(text)
        if match:
            return int(match.group(1))
        bare = _BARE_YEAR.search(text)
        return int(bare.group(1)) if bare else None

    def _identifiers(self, text: str) -> dict[str, str]:
        out: dict[str, str] = {}
        ticker = _TICKER.search(text)
        if ticker:
            out["ticker"] = ticker.group(1)
        cik = _CIK.search(text)
        if cik:
            out["cik"] = cik.group(1)
        return out

    def _critical_figures(self, document: ExtractedDocument) -> tuple[CriticalFigure, ...]:
        figures: list[CriticalFigure] = []
        for page in document.pages:
            for block in page.text_blocks:
                low = block.text.lower()
                for label in _CRITICAL_LABELS:
                    idx = low.find(label)
                    if idx == -1:
                        continue
                    tail = block.text[idx + len(label) : idx + len(label) + 40]
                    value = _FIGURE_VALUE.search(tail)
                    if value:
                        figures.append(
                            CriticalFigure(label=label, value=value.group(0).strip(), page=page.page_number)
                        )
        return tuple(figures)

    def _table_inventory(self, document: ExtractedDocument) -> tuple[TableInventoryEntry, ...]:
        entries: list[TableInventoryEntry] = []
        for page_no, table in document.tables():
            entries.append(
                TableInventoryEntry(
                    table_id=table.table_id,
                    page=page_no,
                    n_rows=len(table.rows),
                    n_cols=len(table.rows[0]) if table.rows else 0,
                    statement_type=self._statement_type(table.caption),
                )
            )
        return tuple(entries)

    def _statement_type(self, caption: str | None) -> str | None:
        if not caption:
            return None
        low = caption.lower()
        if "balance" in low:
            return "balance_sheet"
        if "income" in low or "operations" in low:
            return "income_statement"
        if "cash flow" in low:
            return "cash_flow"
        return None
