"""Context-budget assembly (rag-design.md §4) — slot-fill, never global pool.

The ranked per-repository candidates are assembled into one grounded context by
**weighted budget**, not by score comparison. Each role gets a guaranteed share
of the token budget (evidence largest, scaffold a fixed slot, exemplars bounded),
so a similar exemplar can never crowd out the financial evidence:

    scaffold first (the required structure) → evidence into the budget (the cited
    facts, each tagged ``[F#]``) → exemplars as bounded style guidance.

The budget is sized against the **smaller** production SLM window
(``min(ContextBudget.total_context_tokens, gateway.context_window)``) and measured
with the gateway's own ``count_tokens``, so the assembler never relies on a larger
prototype window. The assembled chunks are recorded per repository so context
contribution % and citations are derived from exactly what entered the prompt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core.policies.retrieval import ContextBudget
from app.domain.ports.llm_gateway import LLMGatewayPort
from app.domain.ports.vector_store import ScoredChunk
from app.domain.repositories.repository import Repository

_SYSTEM_PROMPT = (
    "You are a financial proposal writer. Follow the SCAFFOLD structure exactly. "
    "Every figure or factual claim MUST come from the EVIDENCE section and cite its "
    "[F#] tag — never invent figures and never take figures from the EXEMPLARS, "
    "which inform tone and framing only. If the evidence does not support a claim, "
    "omit it."
)


@dataclass(frozen=True, slots=True)
class ScaffoldSlot:
    """One scaffold-derived section the generator must fill (ordered, locked)."""

    slot: str
    heading: str
    text: str
    order: int


@dataclass(frozen=True, slots=True)
class AssembledContext:
    """The grounded context: blocks for the prompt + the chunks behind them."""

    system: str
    evidence_block: str
    exemplar_block: str
    scaffold_slots: tuple[ScaffoldSlot, ...]
    evidence_chunks: tuple[ScoredChunk, ...]
    exemplar_chunks: tuple[ScoredChunk, ...]
    scaffold_chunks: tuple[ScoredChunk, ...]
    tokens_by_repository: dict[Repository, int] = field(default_factory=dict)
    max_output_tokens: int = 1024

    @property
    def has_scaffold(self) -> bool:
        return bool(self.scaffold_slots)


def evidence_tag(ordinal: int) -> str:
    """Stable citation tag for the n-th included evidence chunk."""
    return f"F{ordinal + 1}"


class ContextAssembler:
    """Allocates the context budget and renders the grounded prompt blocks."""

    def __init__(self, *, gateway: LLMGatewayPort, budget: ContextBudget) -> None:
        self._gateway = gateway
        self._budget = budget

    async def assemble(
        self,
        *,
        scaffold: list[ScoredChunk],
        evidence: list[ScoredChunk],
        exemplars: list[ScoredChunk],
        max_output_tokens: int = 1024,
    ) -> AssembledContext:
        total = min(self._budget.total_context_tokens, self._gateway.context_window)
        scaffold_budget = int(total * self._budget.scaffold_share)
        evidence_budget = int(total * self._budget.evidence_share)
        exemplar_budget = int(total * self._budget.exemplar_share)

        kept_scaffold = await self._fill(scaffold, scaffold_budget)
        kept_evidence = await self._fill(evidence, evidence_budget)
        kept_exemplars = await self._fill(exemplars, exemplar_budget)

        slots = _build_scaffold_slots(kept_scaffold)
        evidence_block = "\n\n".join(
            f"[{evidence_tag(i)}] {c.chunk.text}" for i, c in enumerate(kept_evidence)
        )
        exemplar_block = "\n\n".join(c.chunk.text for c in kept_exemplars)

        tokens = {
            Repository.TEMPLATE: await self._count(kept_scaffold),
            Repository.FINANCIAL: await self._count(kept_evidence),
            Repository.PROPOSAL: await self._count(kept_exemplars),
        }
        return AssembledContext(
            system=_SYSTEM_PROMPT,
            evidence_block=evidence_block,
            exemplar_block=exemplar_block,
            scaffold_slots=slots,
            evidence_chunks=tuple(kept_evidence),
            exemplar_chunks=tuple(kept_exemplars),
            scaffold_chunks=tuple(kept_scaffold),
            tokens_by_repository=tokens,
            max_output_tokens=max_output_tokens,
        )

    async def _fill(self, candidates: list[ScoredChunk], budget: int) -> list[ScoredChunk]:
        """Greedily take best-first candidates while under the token budget."""
        kept: list[ScoredChunk] = []
        used = 0
        for candidate in candidates:
            cost = await self._gateway.count_tokens(candidate.chunk.text)
            if kept and used + cost > budget:
                break  # keep at least one if it alone exceeds the slot budget
            kept.append(candidate)
            used += cost
            if used >= budget:
                break
        return kept

    async def _count(self, chunks: list[ScoredChunk]) -> int:
        total = 0
        for c in chunks:
            total += await self._gateway.count_tokens(c.chunk.text)
        return total

    @staticmethod
    def _heading(text: str, index: int) -> str:
        for line in text.splitlines():
            stripped = line.strip()
            if stripped:
                return stripped[:80]
        return f"Section {index + 1}"


# A template document defines the proposal structure as numbered sections
# ("1. Executive Summary", "2. Market Opportunity", …). The scaffold is split on
# those headings so one template doc yields one locked section per heading; a
# template with no numbered headings stays a single section (back-compatible).
_SECTION_HEADING = re.compile(r"^\s*\d+(?:\.\d+)*[.)]?\s+(\S.*?)\s*$")


def _split_template_sections(text: str) -> list[tuple[str, str]]:
    """Return ``(heading, body)`` per numbered section; ``[]`` if none are found."""
    sections: list[tuple[str, list[str]]] = []
    for line in text.splitlines():
        match = _SECTION_HEADING.match(line)
        if match:
            sections.append((match.group(1).strip(), []))
        elif sections:
            sections[-1][1].append(line)
    return [(h, "\n".join(b).strip()) for h, b in sections]


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _build_scaffold_slots(kept_scaffold: list[ScoredChunk]) -> tuple[ScaffoldSlot, ...]:
    """Expand each scaffold chunk into one or more ordered, locked section slots."""
    slots: list[ScaffoldSlot] = []
    for chunk in kept_scaffold:
        default_slot = str(chunk.chunk.metadata.get("subtype") or "section")
        sections = _split_template_sections(chunk.chunk.text)
        if sections:
            for heading, body in sections:
                slots.append(
                    ScaffoldSlot(
                        slot=_slugify(heading) or default_slot,
                        heading=heading,
                        text=body,
                        order=len(slots),
                    )
                )
        else:
            slots.append(
                ScaffoldSlot(
                    slot=default_slot,
                    heading=ContextAssembler._heading(chunk.chunk.text, len(slots)),
                    text=chunk.chunk.text,
                    order=len(slots),
                )
            )
    return tuple(slots)
