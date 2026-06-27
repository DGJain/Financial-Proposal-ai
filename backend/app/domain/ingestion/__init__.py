"""Ingestion-pipeline domain: layout-aware extraction model, redaction ledger,
and the auditable ingestion records produced by the financial vertical slice."""

from app.domain.ingestion.anonymization import (
    AnonymizationFinding,
    AnonymizationFindingKind,
    AnonymizationReport,
)
from app.domain.ingestion.enums import (
    ContentType,
    IngestionStatus,
    ReviewReason,
)
from app.domain.ingestion.extracted import (
    BBox,
    ExtractedDocument,
    ExtractedFigure,
    ExtractedPage,
    ExtractedTable,
    TextBlock,
)
from app.domain.ingestion.lineage import (
    HumanReviewItem,
    IngestionLineage,
    IngestionResult,
)
from app.domain.ingestion.redaction import (
    NormalizedDocument,
    RedactionEntry,
    RedactionKind,
    RedactionLedger,
)

__all__ = [
    "AnonymizationFinding",
    "AnonymizationFindingKind",
    "AnonymizationReport",
    "BBox",
    "ContentType",
    "ExtractedDocument",
    "ExtractedFigure",
    "ExtractedPage",
    "ExtractedTable",
    "HumanReviewItem",
    "IngestionLineage",
    "IngestionResult",
    "IngestionStatus",
    "NormalizedDocument",
    "RedactionEntry",
    "RedactionKind",
    "RedactionLedger",
    "ReviewReason",
    "TextBlock",
]
