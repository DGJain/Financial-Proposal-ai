"""Proposal generation (rag-design.md §1 generate stage).

Generates the proposal **section by section against the scaffold**: the template
defines the locked structure (ordered slots), and each section is filled from the
shared grounded context (evidence + exemplars) via ``LLMGatewayPort``. Binding
sections to template slots is what lets the editor lock structure while keeping
prose editable, and lets confidence flag individual low-grounding sections.

The combined section text is returned alongside the ``Proposal`` so numeric
verification can trace every figure in the *whole* output back to evidence before
the draft is accepted. With no scaffold (template branch empty) a single fallback
section is produced so a grounded run still yields a document.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from app.domain.generation.brief import GenerationBrief
from app.domain.ports.llm_gateway import GenerationRequest, LLMGatewayPort
from app.domain.proposals.enums import ProposalStatus
from app.domain.proposals.proposal import Proposal, ProposalSection, ProposalVersion
from app.modules.rag.assembly.assembler import AssembledContext, ScaffoldSlot

# Lines a small model tends to echo back from the prompt — the scaffold/brief/
# instruction labels — plus any letter greeting/sign-off it may invent. Stripped so
# each section body is clean advisory prose, not a transcript of its own instructions
# or a stray "Dear …/Yours sincerely" wrapper. ``[metric]`` placeholders are kept.
_ECHO_LINE = re.compile(
    r"^\s*(EVIDENCE|EXEMPLARS?|SCAFFOLD|BRIEF|PROPOSAL|TYPE|ENTITY|FISCAL[ _]?YEAR|"
    r"SECTOR|LINE[ _]?ITEMS?|INSTRUCTIONS?|SECTION INTENT|SECTION|CONTEXT|GUIDANCE|"
    r"CLIENT[ _]?MATERIAL|ENGAGEMENT BRIEF|RETURN ONLY|WRITE THE|OUTPUT|TITLE)\s*[:\-—]"
    r"|^\s*\[F\d+\]"
    r"|^\s*(Dear\b|Yours\s+(sincerely|faithfully)|Best\s+(regards|wishes)|"
    r"Kind\s+regards|Warm\s+regards|Sincerely\b)"
    r"|^\s*\[(your|client|recipient|signatory|name|position|contact|sender)\b",
    re.IGNORECASE,
)

# A Markdown section heading the content-driven path emits ("## Executive Summary").
_HEADING_RE = re.compile(r"^\s{0,3}#{1,4}\s+(.+?)\s*$")


def _parse_markdown_sections(text: str) -> list[tuple[str | None, str]]:
    """Split model output into (heading, body) pairs on Markdown ``#`` headings.

    Text before the first heading becomes a leading (heading=None) block. Leading
    section numbers in a heading ("1. ", "2) ") are stripped — we re-number on export.
    """
    sections: list[tuple[str | None, str]] = []
    heading: str | None = None
    body_lines: list[str] = []
    for raw in text.splitlines():
        m = _HEADING_RE.match(raw)
        if m:
            body = "\n".join(body_lines).strip()
            if heading is not None or body:
                sections.append((heading, body))
            heading = re.sub(r"^[\d.)\s]+", "", m.group(1)).strip() or m.group(1).strip()
            body_lines = []
        else:
            body_lines.append(raw)
    body = "\n".join(body_lines).strip()
    if heading is not None or body:
        sections.append((heading, body))
    return sections


# Words that mark a line as a table caption/title rather than body prose.
_CAPTION_KEYWORDS = re.compile(
    r"\b(metrics?|kpis?|performance|summary|results?|financials?|figures?|"
    r"projections?|statement|highlights?|overview|breakdown|table|data|"
    r"forecast|outlook|scorecard)\b",
    re.IGNORECASE,
)


def _table_caption(material: str, fallback: str) -> str:
    """Find the heading the client gave their data in the source doc (e.g. "FY2025
    Key Performance Metrics") so the reproduced table keeps the user's own title."""
    for raw in material.splitlines():
        line = raw.strip().rstrip(":").strip()
        if not line or "|" in line or line.startswith("["):
            continue  # table rows / our "[Attached content — …]" markers
        if line.lower().startswith(("source", "note", "the ", "this ", "please", "we ")):
            continue  # sentences/captions we don't want as a heading
        words = line.split()
        if 1 <= len(words) <= 9 and not line.endswith(".") and _CAPTION_KEYWORDS.search(line):
            return line
    return fallback


def _fallback_caption(attachment_names: list[str]) -> str:
    """A readable heading from the attachment filename when no caption is in the text."""
    for name in attachment_names:
        stem = re.split(r"\.[A-Za-z0-9]+$", name)[0]
        stem = stem.replace("_", " ").replace("-", " ").strip()
        if stem:
            return stem.title()
    return "Key Figures"


def _extract_pipe_tables(text: str) -> list[str]:
    """Pull verbatim data tables (runs of ≥2 consecutive ``a | b | c`` lines) out of
    client material, so they can be reproduced exactly rather than retyped by the model."""
    tables: list[str] = []
    block: list[str] = []
    for line in text.splitlines():
        if line.strip() and "|" in line:
            block.append(line.strip())
        else:
            if len(block) >= 2:
                tables.append("\n".join(block))
            block = []
    if len(block) >= 2:
        tables.append("\n".join(block))
    # De-duplicate while keeping order (extractors often emit a table twice).
    seen: set[str] = set()
    return [t for t in tables if not (t in seen or seen.add(t))]


def _letters(text: str) -> str:
    return re.sub(r"[^a-z]", "", text.lower())


def _sanitize_section(text: str, heading: str) -> str:
    """Drop any prompt scaffolding the model echoed back; keep the real prose."""
    heading_key = _letters(heading)
    kept: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if _ECHO_LINE.match(stripped):
            continue
        # An echoed bare section title (with or without its leading number).
        if heading_key and _letters(stripped) == heading_key:
            continue
        kept.append(line)
    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
    return cleaned or text.strip()  # never return empty if the model only echoed


@dataclass(frozen=True, slots=True)
class GeneratedDraft:
    """A generated proposal plus the concatenated text for numeric verification."""

    proposal: Proposal
    output_text: str


class ProposalGenerator:
    def __init__(self, gateway: LLMGatewayPort) -> None:
        self._gateway = gateway

    async def generate(
        self,
        *,
        brief: GenerationBrief,
        context: AssembledContext,
        gen_id: str,
        proposal_id: str,
        engagement_id: str,
        template_id: str,
        requested_by: str,
        ts: datetime,
        style_only: bool = False,
    ) -> GeneratedDraft:
        slots = context.scaffold_slots or (
            ScaffoldSlot(slot="proposal", heading=brief.title, text="", order=0),
        )
        sections: list[ProposalSection] = []
        for slot in slots:
            result = await self._gateway.generate(
                self._request(brief, context, slot, style_only=style_only)
            )
            sections.append(
                ProposalSection(
                    section_id=f"{proposal_id}-s{slot.order:02d}",
                    slot=slot.slot,
                    heading=slot.heading,
                    order=slot.order,
                    body=_sanitize_section(result.text, slot.heading),
                )
            )

        version = ProposalVersion(
            version_no=1,
            sections=tuple(sections),
            created_ts=ts,
            created_by=requested_by,
            status=ProposalStatus.DRAFT,
        )
        proposal = Proposal(
            proposal_id=proposal_id,
            gen_id=gen_id,
            engagement_id=engagement_id,
            template_id=template_id,
            versions=(version,),
            status=ProposalStatus.DRAFT,
        )
        output_text = "\n".join(s.body for s in sections)
        return GeneratedDraft(proposal=proposal, output_text=output_text)

    async def generate_from_content(
        self,
        *,
        brief: GenerationBrief,
        context: AssembledContext,
        gen_id: str,
        proposal_id: str,
        engagement_id: str,
        template_id: str,
        requested_by: str,
        ts: datetime,
        allow_evidence: bool,
    ) -> GeneratedDraft:
        """Attachment-driven generation: one pass turns the client material into a
        proposal with a dynamic number of sections, and the client's data table(s)
        are reproduced verbatim as a labelled section. ``allow_evidence`` lets cited
        figures through too when the run is grounded."""
        material = brief.attachment_text()
        result = await self._gateway.generate(
            self._content_request(brief, context, material, allow_evidence=allow_evidence)
        )

        sections: list[ProposalSection] = []
        order = 0
        for heading, body in _parse_markdown_sections(result.text):
            clean = _sanitize_section(body, heading or "")
            if not clean.strip():
                continue
            head = heading or (brief.title if order == 0 else f"Section {order + 1}")
            sections.append(
                ProposalSection(
                    section_id=f"{proposal_id}-s{order:02d}",
                    slot="content",
                    heading=head,
                    order=order,
                    body=clean,
                )
            )
            order += 1

        if not sections:  # model returned nothing usable → still produce a document
            sections.append(
                ProposalSection(
                    section_id=f"{proposal_id}-s00",
                    slot="content",
                    heading=brief.title,
                    order=0,
                    body=_sanitize_section(result.text, brief.title),
                )
            )
            order = 1

        tables = _extract_pipe_tables(material)
        if tables:
            caption = _table_caption(
                material, _fallback_caption([a.name for a in brief.attachments])
            )
            for i, table in enumerate(tables):
                heading = caption if i == 0 else f"{caption} ({i + 1})"
                sections.append(
                    ProposalSection(
                        section_id=f"{proposal_id}-s{order:02d}",
                        slot="data",
                        heading=heading,
                        order=order,
                        body=table,
                    )
                )
                order += 1

        version = ProposalVersion(
            version_no=1,
            sections=tuple(sections),
            created_ts=ts,
            created_by=requested_by,
            status=ProposalStatus.DRAFT,
        )
        proposal = Proposal(
            proposal_id=proposal_id,
            gen_id=gen_id,
            engagement_id=engagement_id,
            template_id=template_id,
            versions=(version,),
            status=ProposalStatus.DRAFT,
        )
        output_text = "\n".join(s.body for s in sections)
        return GeneratedDraft(proposal=proposal, output_text=output_text)

    def _content_request(
        self,
        brief: GenerationBrief,
        context: AssembledContext,
        material: str,
        *,
        allow_evidence: bool,
    ) -> GenerationRequest:
        for_entity = f" for {brief.entity}" if brief.entity else ""
        figure_rule = (
            "Use figures and data ONLY as they appear in the CLIENT MATERIAL. You MUST "
            "NOT introduce, infer, or alter any number that is not present in the CLIENT "
            "MATERIAL — do not invent figures."
        )
        evidence = ""
        if allow_evidence and context.evidence_block:
            figure_rule += (
                " You may additionally state a figure that appears verbatim in EVIDENCE "
                "with its [F#] tag, citing that tag."
            )
            evidence = f"\n\nEVIDENCE:\n{context.evidence_block}"
        system = (
            f"{context.system}\n\n{figure_rule}{evidence}\n\n"
            f"EXEMPLARS (house style and tone only — never a source of figures):\n"
            f"{context.exemplar_block or '(none)'}"
        )
        guidance = brief.instructions.strip()
        guidance_line = f"\nThe client's request: {guidance}" if guidance else ""
        prompt = (
            f"Using the CLIENT MATERIAL below, write a professional advisory proposal"
            f"{for_entity}.{guidance_line}\n"
            f"Organise it into clearly titled sections using Markdown '## ' headings — "
            f"create as many sections as the material warrants (for example: Executive "
            f"Summary, then a section for each major theme or dataset in the material, and "
            f"a closing Recommendation). Weave the client's data and figures into the "
            f"narrative faithfully. Write in the confident advisory voice of the EXEMPLARS "
            f"as continuous prose under each heading — no greeting, no sign-off, and do not "
            f"repeat these instructions.\n\n"
            f"CLIENT MATERIAL:\n{material}"
        )
        return GenerationRequest(
            system=system,
            prompt=prompt,
            max_output_tokens=context.max_output_tokens,
            temperature=0.0,
        )

    def _request(
        self,
        brief: GenerationBrief,
        context: AssembledContext,
        slot: ScaffoldSlot,
        *,
        style_only: bool = False,
    ) -> GenerationRequest:
        # The grounded context goes in the SYSTEM message and the user turn is a short
        # directive — small models echo far less when the bulky context isn't in the
        # turn they're asked to continue. The output is also sanitised afterwards.
        if style_only:
            figure_rule = (
                "No financial evidence is available, so write qualitative, FIGURE-FREE "
                "prose. Do NOT state any specific monetary amount, percentage, count or "
                "other number, and do NOT invent any. Where a specific figure would "
                "naturally appear, write a short bracketed placeholder such as "
                "[projected return], [investment requirement] or [timeframe] instead. "
                "Mirror the advisory voice, structure and phrasing of the EXEMPLARS closely."
            )
            evidence = ""
        else:
            figure_rule = (
                "State a number ONLY if it appears verbatim in EVIDENCE with its [F#] tag, "
                "and cite that tag; otherwise describe it qualitatively. Never take a figure "
                "from the EXEMPLARS."
            )
            evidence = (
                f"\n\nEVIDENCE (the only source of facts):\n{context.evidence_block or '(none)'}"
            )

        system = (
            f"{context.system}\n\n{figure_rule}{evidence}\n\n"
            f"EXEMPLARS (house style and tone only — never a source of figures):\n"
            f"{context.exemplar_block or '(none)'}"
        )

        for_entity = f" for {brief.entity}" if brief.entity else ""
        intent = slot.text.strip() if slot.text and slot.text.strip() else ""
        intent_line = f"\nWhat this section should cover: {intent}" if intent else ""
        guidance = brief.instructions.strip()
        guidance_line = f"\nThe client's request: {guidance}" if guidance else ""
        prompt = (
            f'Write the "{slot.heading}" section of a professional proposal'
            f"{for_entity}, as continuous prose (no greeting, no sign-off — this is a "
            f"section of a report, not a letter)."
            f"{intent_line}{guidance_line}\n\n"
            f"Return ONLY the finished prose for this section — two or three short, "
            f"confident paragraphs in the advisory voice of the EXEMPLARS. Do not repeat "
            f"the section title, these instructions, or any labels."
        )
        return GenerationRequest(
            system=system,
            prompt=prompt,
            max_output_tokens=context.max_output_tokens,
            temperature=0.0,
        )
