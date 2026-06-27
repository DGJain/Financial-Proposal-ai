"""Echo gateway — deterministic local/test implementation of ``LLMGatewayPort``.

Generates a predictable, non-network response so the orchestration, streaming, and
guardrail wiring can be exercised end-to-end without a model server or API key.
Selected by the composition root when ``ENVIRONMENT=local``. It never invents
figures — it echoes a bounded summary of the assembled prompt — which keeps local
runs safe to show in the grounding/figure-retention gates.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from app.domain.ports.llm_gateway import GenerationRequest, GenerationResult

_CONTEXT_WINDOW = 8192


def _render(request: GenerationRequest) -> str:
    return (
        "[echo-draft] Generated from the assembled grounded prompt "
        f"({len(request.prompt)} chars, system={len(request.system)} chars). "
        "This deterministic placeholder contains no figures."
    )


class EchoGateway:
    @property
    def model_id(self) -> str:
        return "echo-local"

    @property
    def context_window(self) -> int:
        return _CONTEXT_WINDOW

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        text = _render(request)
        return GenerationResult(
            text=text,
            input_tokens=await self.count_tokens(request.system + request.prompt),
            output_tokens=await self.count_tokens(text),
            model_id=self.model_id,
        )

    async def stream(self, request: GenerationRequest) -> AsyncIterator[str]:
        for token in _render(request).split(" "):
            yield token + " "

    async def count_tokens(self, text: str) -> int:
        # Whitespace heuristic — adequate for budgeting in local/test runs.
        return len(text.split())
