"""Template layered metadata (document-intelligence U-2, template schema).

Derives the scaffold repository's metadata: the template type, the placeholder
slots it exposes (so generation knows what it must fill), and its lifecycle
``status`` (draft/approved/deprecated). Slots and structure come from the
document; ``template_type``/``status`` may be supplied as curation hints.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.domain.documents.enums import TemplateSubtype
from app.domain.ingestion.extracted import ExtractedDocument
from app.modules.ingestion.quality.placeholders import Slot, find_slots

_SUBTYPE_MARKERS: tuple[tuple[TemplateSubtype, tuple[str, ...]], ...] = (
    (TemplateSubtype.EXECUTIVE_SUMMARY, ("executive summary",)),
    (TemplateSubtype.PRICING, ("pricing", "fees")),
    (TemplateSubtype.TIMELINE, ("timeline", "schedule")),
    (TemplateSubtype.RISK_ASSESSMENT, ("risk assessment", "risk")),
    (TemplateSubtype.PROPOSAL_STRUCTURE, ("proposal structure", "structure", "outline")),
)


@dataclass(frozen=True, slots=True)
class TemplateMetadata:
    """Layered metadata for a template scaffold."""

    subtype: TemplateSubtype
    status: str = "approved"
    slot_names: tuple[str, ...] = ()

    @property
    def subtype_value(self) -> str:
        return self.subtype.value

    def chunk_metadata(self) -> dict[str, str | int]:
        md: dict[str, str | int] = {
            "subtype": self.subtype.value,
            "status": self.status,  # enables status=approved retrieval filter
            "slot_count": len(self.slot_names),
        }
        return md


class TemplateMetadataExtractor:
    """Extracts template layered metadata from a normalized document + hints."""

    def extract(
        self,
        document: ExtractedDocument,
        *,
        hints: Mapping[str, str] | None = None,
    ) -> TemplateMetadata:
        hints = hints or {}
        lowered = document.full_text.lower()
        slots: list[Slot] = [
            slot for page in document.pages for b in page.text_blocks for slot in find_slots(b.text)
        ]
        names = tuple(dict.fromkeys(slot.name for slot in slots))  # de-dup, keep order
        return TemplateMetadata(
            subtype=self._subtype(lowered),
            status=hints.get("status", "approved"),
            slot_names=names,
        )

    def _subtype(self, lowered: str) -> TemplateSubtype:
        for subtype, markers in _SUBTYPE_MARKERS:
            if any(marker in lowered for marker in markers):
                return subtype
        return TemplateSubtype.PROPOSAL_STRUCTURE
