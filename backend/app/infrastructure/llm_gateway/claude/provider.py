"""Claude gateway — prototype provider for ``LLMGatewayPort``.

Permitted **only outside production** (settings enforce SLM in prod). ``anthropic``
is imported lazily. This is a thin adapter: it maps the domain ``GenerationRequest``
onto the Messages API and exposes streaming. Token counting uses a heuristic to
avoid extra round-trips; swap to the API counter if exact budgeting is needed.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.core.config import AISettings
from app.domain.ports.llm_gateway import GenerationRequest, GenerationResult

# Claude's context window is far larger than the SLM's; the assembler is still
# budgeted against the smaller prod window so behavior is portable.
_CONTEXT_WINDOW = 200_000


class ClaudeGateway:
    def __init__(self, settings: AISettings) -> None:
        if not settings.claude_api_key:
            raise ValueError("AI_CLAUDE_API_KEY is required for the Claude gateway")
        self._model = settings.claude_model
        self._api_key = settings.claude_api_key
        self._timeout = settings.request_timeout_seconds
        self._client: Any | None = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            import anthropic  # lazy

            self._client = anthropic.AsyncAnthropic(api_key=self._api_key, timeout=self._timeout)
        return self._client

    @property
    def model_id(self) -> str:
        return self._model

    @property
    def context_window(self) -> int:
        return _CONTEXT_WINDOW

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        client = self._ensure_client()
        # NOTE: no `temperature`/`top_p` — sampling params are removed on Opus 4.8/4.7
        # (they 400). Omitting them is valid on every model, so the gateway stays
        # model-agnostic across the Claude lineup.
        message = await client.messages.create(
            model=self._model,
            system=request.system,
            messages=[{"role": "user", "content": request.prompt}],
            max_tokens=request.max_output_tokens,
            stop_sequences=list(request.stop) or None,
        )
        text = "".join(block.text for block in message.content if block.type == "text")
        return GenerationResult(
            text=text,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
            model_id=self._model,
        )

    async def stream(self, request: GenerationRequest) -> AsyncIterator[str]:
        client = self._ensure_client()
        async with client.messages.stream(
            model=self._model,
            system=request.system,
            messages=[{"role": "user", "content": request.prompt}],
            max_tokens=request.max_output_tokens,
            stop_sequences=list(request.stop) or None,
        ) as stream:
            async for text in stream.text_stream:
                yield text

    async def count_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)  # heuristic ~4 chars/token
