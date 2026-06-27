"""Redaction ledger — the auditable record of PII/MNPI removed at ingestion.

Kept **separate from the information-loss vector** (document-intelligence.md U-2):
redaction is intentional, policy-driven removal, not extraction failure, so it
must never count against EQS. The ledger records *that* and *where* something was
redacted (kind, pattern, page, span, placeholder) but never the original
sensitive value — the ledger itself must be safe to retain and audit.

The detected sensitivity kinds drive the document's ``SensitivityFlag`` set and,
in turn, its ACL/classification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from app.domain.documents.enums import SensitivityFlag
from app.domain.ingestion.extracted import ExtractedDocument


class RedactionKind(StrEnum):
    """Category of redacted content, mapped onto a ``SensitivityFlag``."""

    PII = "pii"
    MNPI = "mnpi"

    def to_sensitivity(self) -> SensitivityFlag:
        return SensitivityFlag(self.value)


@dataclass(frozen=True, slots=True)
class RedactionEntry:
    """One redaction event — location and category only, never the raw value."""

    kind: RedactionKind
    pattern_name: str  # e.g. "email", "ssn", "mnpi_marker"
    page: int
    span_start: int
    span_end: int
    placeholder: str  # what replaced the value in normalized text


@dataclass(frozen=True, slots=True)
class RedactionLedger:
    """Immutable collection of redaction events for one document."""

    entries: tuple[RedactionEntry, ...] = field(default_factory=tuple)

    @property
    def count(self) -> int:
        return len(self.entries)

    def counts_by_kind(self) -> dict[RedactionKind, int]:
        out: dict[RedactionKind, int] = {}
        for entry in self.entries:
            out[entry.kind] = out.get(entry.kind, 0) + 1
        return out

    def sensitivity_flags(self) -> frozenset[SensitivityFlag]:
        """The ``SensitivityFlag`` set implied by what was redacted."""
        return frozenset(entry.kind.to_sensitivity() for entry in self.entries)


@dataclass(frozen=True, slots=True)
class NormalizedDocument:
    """Cleaned + redacted document paired with its redaction ledger.

    The ``document`` is an ``ExtractedDocument`` whose text has had PII/MNPI
    replaced by placeholders; the ``redaction`` ledger explains what was removed.
    Financial figures are deliberately never redacted (they must survive for CFR).
    """

    document: ExtractedDocument
    redaction: RedactionLedger
