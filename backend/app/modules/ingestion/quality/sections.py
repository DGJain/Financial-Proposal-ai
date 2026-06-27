"""Proposal section taxonomy + detection (shared by metadata, chunking, gate).

Section Coverage (U-4) and section-semantic chunking (U-3) both need the same
notion of "which proposal sections are present." Centralizing the taxonomy and a
deterministic keyword detector here keeps those stages consistent — a section the
chunker labels is the same section the gate counts toward coverage.
"""

from __future__ import annotations

from enum import StrEnum

from app.domain.documents.enums import ProposalSubtype


class ProposalSectionType(StrEnum):
    """Canonical proposal sections (ui-design / document-intelligence U-2)."""

    EXECUTIVE_SUMMARY = "executive_summary"
    APPROACH = "approach"
    TEAM = "team"
    PRICING = "pricing"
    TIMELINE = "timeline"
    RISK = "risk"


# Heading/keyword cues per section, lower-cased substring match.
_SECTION_CUES: dict[ProposalSectionType, tuple[str, ...]] = {
    ProposalSectionType.EXECUTIVE_SUMMARY: ("executive summary", "exec summary", "overview"),
    ProposalSectionType.APPROACH: ("approach", "methodology", "our solution", "scope of work"),
    ProposalSectionType.TEAM: ("team", "key personnel", "our people", "qualifications"),
    ProposalSectionType.PRICING: ("pricing", "fees", "investment", "cost", "commercials"),
    ProposalSectionType.TIMELINE: ("timeline", "schedule", "milestones", "phases", "plan"),
    ProposalSectionType.RISK: ("risk", "mitigation", "assumptions"),
}

# Sections expected per subtype (denominator of Section Coverage = |expected|).
_EXPECTED: dict[ProposalSubtype, frozenset[ProposalSectionType]] = {
    ProposalSubtype.PAST_PROPOSAL: frozenset(ProposalSectionType),
    ProposalSubtype.STATEMENT_OF_WORK: frozenset({
        ProposalSectionType.APPROACH,
        ProposalSectionType.PRICING,
        ProposalSectionType.TIMELINE,
    }),
    ProposalSubtype.PITCH: frozenset({
        ProposalSectionType.EXECUTIVE_SUMMARY,
        ProposalSectionType.APPROACH,
        ProposalSectionType.TEAM,
    }),
    ProposalSubtype.CASE_STUDY: frozenset({
        ProposalSectionType.EXECUTIVE_SUMMARY,
        ProposalSectionType.APPROACH,
    }),
    ProposalSubtype.METHODOLOGY: frozenset({
        ProposalSectionType.APPROACH,
    }),
}

_DEFAULT_EXPECTED: frozenset[ProposalSectionType] = frozenset({
    ProposalSectionType.EXECUTIVE_SUMMARY,
    ProposalSectionType.APPROACH,
    ProposalSectionType.PRICING,
    ProposalSectionType.TIMELINE,
})


def expected_sections(subtype: ProposalSubtype) -> frozenset[ProposalSectionType]:
    return _EXPECTED.get(subtype, _DEFAULT_EXPECTED)


def detect_section(text: str) -> ProposalSectionType | None:
    """Classify a block of text to a section by its leading cue, if any."""
    low = text.lower()
    for section, cues in _SECTION_CUES.items():
        if any(cue in low for cue in cues):
            return section
    return None


def detected_sections(texts: list[str]) -> set[ProposalSectionType]:
    found: set[ProposalSectionType] = set()
    for text in texts:
        section = detect_section(text)
        if section is not None:
            found.add(section)
    return found
