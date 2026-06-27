"""Numeric verification + citation binding (rag-design.md §1 guardrails, §6b).

The hard rule: **every figure in the generated proposal must trace to a cited
financial (evidence) chunk.** This stage is the enforcement point:

1. Each financial evidence chunk that entered the assembled context becomes a
   citation candidate (citations may only resolve to ``repo_financial``).
2. Every monetary/structured figure in the output is traced:
   * present in a cited financial chunk → grounded (fine);
   * present only in an exemplar/template chunk → **leakage** (a past client's
     figure leaking into a new proposal) → ``BLOCK_REGENERATE``;
   * present in neither → **ungrounded** (invented) → ``BLOCK_REGENERATE``.

A "figure" is deliberately narrow — a currency-marked or thousands-grouped number
(``$5,000,000``, ``5,000,000``, ``1,234.56``) — so bare counts/years in boilerplate
are not mistaken for financial claims. Leaked/ungrounded figures are returned as
non-financial "claims" so the contribution factual share drops below its floor,
which the factual-health guardrail reads as the signature of figure leakage.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.domain.generation.enums import GenerationGateVerdict
from app.domain.generation.generation_event import Citation
from app.domain.ports.vector_store import ScoredChunk
from app.domain.repositories.repository import Repository
from app.modules.proposal_generation.lineage import source_name_of

# A figure must carry a currency marker OR thousands grouping (optionally a
# decimal) — bare integers like "100" or years like "2024" are not figures.
_FIGURE = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?|\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b")


def extract_figures(text: str) -> set[str]:
    """Normalized set of monetary/structured figures present in ``text``."""
    return {_normalize(m.group(0)) for m in _FIGURE.finditer(text)}


def _normalize(raw: str) -> str:
    return re.sub(r"[^0-9.]", "", raw).rstrip(".") or raw


@dataclass(frozen=True, slots=True)
class LeakedFigure:
    """A figure in the output that did not trace to cited financial evidence."""

    figure: str
    repository: Repository  # where it *did* come from (exemplar/template), or FINANCIAL-absent
    chunk_id: str | None
    source_name: str | None


@dataclass(frozen=True, slots=True)
class VerificationResult:
    verdict: GenerationGateVerdict
    citations: tuple[Citation, ...] = ()
    leaked: tuple[LeakedFigure, ...] = ()
    ungrounded: tuple[str, ...] = field(default_factory=tuple)

    @property
    def passed(self) -> bool:
        return self.verdict is GenerationGateVerdict.PASS

    def detail(self) -> str:
        parts = []
        if self.leaked:
            parts.append("leaked=" + ",".join(f"{lf.figure}<-{lf.repository.value}" for lf in self.leaked))
        if self.ungrounded:
            parts.append("ungrounded=" + ",".join(self.ungrounded))
        return "; ".join(parts) or "all figures grounded to cited financial evidence"


class NumericVerifier:
    """Binds citations to evidence and traces every output figure to its source."""

    def verify(
        self,
        *,
        output_text: str,
        evidence_chunks: tuple[ScoredChunk, ...],
        nonfinancial_chunks: tuple[ScoredChunk, ...],
        allowed_figures: frozenset[str] = frozenset(),
    ) -> VerificationResult:
        """Trace every output figure to a source.

        ``allowed_figures`` is the set of *client-supplied* figures (normalized,
        from the caller's attachments) that may appear in the output without being
        cited evidence. They are neither grounded nor leaked — they are the user's
        own data, included on the user's authority. A figure that is in none of
        evidence / allowed / non-financial chunks remains **ungrounded** (invented)
        and still blocks, so the no-fabrication guarantee holds even on this path.
        """
        citations = tuple(
            Citation(
                claim_ordinal=i,
                chunk_id=sc.chunk.chunk_id,
                repository=Repository.FINANCIAL,
                source_name=source_name_of(sc.chunk),
                page=sc.chunk.span.page_start,
            )
            for i, sc in enumerate(evidence_chunks)
        )

        evidence_figures = _figure_index(evidence_chunks)
        nonfin_figures = _figure_index(nonfinancial_chunks)

        leaked: list[LeakedFigure] = []
        ungrounded: list[str] = []
        for figure in extract_figures(output_text):
            if figure in evidence_figures:
                continue  # grounded to cited financial evidence
            if figure in allowed_figures:
                continue  # client-supplied (attachment) figure — allowed, unverified
            if figure in nonfin_figures:
                sc = nonfin_figures[figure]
                leaked.append(
                    LeakedFigure(
                        figure=figure,
                        repository=sc.chunk.repository,
                        chunk_id=sc.chunk.chunk_id,
                        source_name=source_name_of(sc.chunk),
                    )
                )
            else:
                ungrounded.append(figure)

        verdict = (
            GenerationGateVerdict.BLOCK_REGENERATE
            if leaked or ungrounded
            else GenerationGateVerdict.PASS
        )
        return VerificationResult(
            verdict=verdict,
            citations=citations,
            leaked=tuple(leaked),
            ungrounded=tuple(ungrounded),
        )


def _figure_index(chunks: tuple[ScoredChunk, ...]) -> dict[str, ScoredChunk]:
    index: dict[str, ScoredChunk] = {}
    for sc in chunks:
        for figure in extract_figures(sc.chunk.text):
            index.setdefault(figure, sc)
    return index
