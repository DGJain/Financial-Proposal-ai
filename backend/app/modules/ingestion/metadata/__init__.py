"""Repository-specific layered-metadata extraction stages (U-2)."""

from app.modules.ingestion.metadata.financial import (
    CriticalFigure,
    FinancialMetadata,
    FinancialMetadataExtractor,
    TableInventoryEntry,
)
from app.modules.ingestion.metadata.proposal import (
    ProposalMetadata,
    ProposalMetadataExtractor,
)
from app.modules.ingestion.metadata.template import (
    TemplateMetadata,
    TemplateMetadataExtractor,
)

__all__ = [
    "CriticalFigure",
    "FinancialMetadata",
    "FinancialMetadataExtractor",
    "ProposalMetadata",
    "ProposalMetadataExtractor",
    "TableInventoryEntry",
    "TemplateMetadata",
    "TemplateMetadataExtractor",
]
