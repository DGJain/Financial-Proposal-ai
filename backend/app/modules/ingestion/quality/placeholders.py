"""Template placeholder detection (shared by the template assessor and chunker).

Templates are parameterizable scaffolds: their value is the slots (``{client_name}``,
``[FEE]``, ``<date>``) that downstream generation fills. Placeholder Integrity
(U-4) and placeholder-preserving chunking (U-3) both rely on the same notion of
"what is a slot and is it well-formed," so it lives here once.

Redaction placeholders (``[REDACTED:PII]``) are deliberately *not* treated as
template slots — they are removed PII, not parameters to fill.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# A candidate slot in any of the three delimiter styles; inner content captured.
_SLOT = re.compile(r"\{([^{}]*)\}|\[([^\[\]]*)\]|<([^<>]*)>")
# A well-formed slot name: starts with a letter, then letters/digits/_/space.
_WELL_FORMED = re.compile(r"[A-Za-z][A-Za-z0-9_ ]*")


@dataclass(frozen=True, slots=True)
class Slot:
    raw: str  # the full delimited token, e.g. "{client_name}"
    name: str  # inner content, e.g. "client_name"
    well_formed: bool


def find_slots(text: str) -> list[Slot]:
    slots: list[Slot] = []
    for match in _SLOT.finditer(text):
        inner = next(g for g in match.groups() if g is not None)
        name = inner.strip()
        if name.upper().startswith("REDACTED"):
            continue  # a redaction marker, not a template parameter
        slots.append(
            Slot(raw=match.group(0), name=name, well_formed=bool(_WELL_FORMED.fullmatch(name)))
        )
    return slots


def placeholder_integrity(slots: list[Slot]) -> float:
    """PI = placeholders_wellformed / placeholders_total (1.0 when none present)."""
    if not slots:
        return 1.0
    return sum(1 for s in slots if s.well_formed) / len(slots)
