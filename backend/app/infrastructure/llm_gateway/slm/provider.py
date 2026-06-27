"""SLM gateway — production provider for ``LLMGatewayPort``.

Calls the internal SLM serving endpoint in the ``ai`` namespace (no egress).
``httpx`` is imported lazily. The context window is the binding constraint the
context assembler budgets against, so it is exposed explicitly.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.core.config import AISettings
from app.domain.ports.llm_gateway import GenerationRequest, GenerationResult

_CONTEXT_WINDOW = 8192


class SlmGateway:
    def __init__(self, settings: AISettings) -> None:
        self._endpoint = settings.slm_endpoint.rstrip("/")
        self._timeout = settings.request_timeout_seconds
        self._client: Any | None = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            import httpx  # lazy

            self._client = httpx.AsyncClient(base_url=self._endpoint, timeout=self._timeout)
        return self._client

    @property
    def model_id(self) -> str:
        return "internal-slm"

    @property
    def context_window(self) -> int:
        return _CONTEXT_WINDOW

    def _payload(self, request: GenerationRequest) -> dict[str, Any]:
        return {
            "system": request.system,
            "prompt": request.prompt,
            "max_tokens": request.max_output_tokens,
            "temperature": request.temperature,
            "stop": list(request.stop),
        }

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        client = self._ensure_client()
        response = await client.post("/generate", json=self._payload(request))
        response.raise_for_status()
        body = response.json()
        return GenerationResult(
            text=body["text"],
            input_tokens=body.get("input_tokens", 0),
            output_tokens=body.get("output_tokens", 0),
            model_id=self.model_id,
        )

    async def stream(self, request: GenerationRequest) -> AsyncIterator[str]:
        client = self._ensure_client()
        async with client.stream("POST", "/generate/stream", json=self._payload(request)) as resp:
            resp.raise_for_status()
            async for chunk in resp.aiter_text():
                if chunk:
                    yield chunk

    async def count_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)  # heuristic; replace with SLM tokenizer if exposed
