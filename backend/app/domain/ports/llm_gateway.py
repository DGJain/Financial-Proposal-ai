"""LLM-gateway port — model abstraction for the enterprise generator.

A single seam decouples use-cases from the provider so the prototype (Claude) and
production (internal SLM) are swapped via configuration only. The interface is
defined against the *smaller* SLM's constraints (context window, streaming) so
the context assembler never relies on a larger prototype window
(rag-design.md / ContextBudget).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    """A fully-assembled, grounded prompt ready for the model."""

    system: str
    prompt: str
    max_output_tokens: int
    temperature: float = 0.2
    stop: Sequence[str] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class GenerationResult:
    """Non-streamed result with usage accounting for metrics."""

    text: str
    input_tokens: int
    output_tokens: int
    model_id: str


@runtime_checkable
class LLMGatewayPort(Protocol):
    @property
    def model_id(self) -> str:
        """Identifier of the active provider/model (recorded with lineage)."""
        ...

    @property
    def context_window(self) -> int:
        """Max input tokens — the binding constraint for context assembly."""
        ...

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        """Produce a complete draft."""
        ...

    def stream(self, request: GenerationRequest) -> AsyncIterator[str]:
        """Stream draft tokens to the Preview pane (text marked provisional
        until the figure/entity-retention gate passes)."""
        ...

    async def count_tokens(self, text: str) -> int:
        """Provider-accurate token count for budgeting the assembled context."""
        ...
