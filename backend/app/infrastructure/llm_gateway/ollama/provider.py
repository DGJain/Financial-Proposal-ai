"""Ollama gateway — local open-weight model provider for ``LLMGatewayPort``.

A free, fully **offline** alternative to the Claude dev escape hatch: it talks to a
local Ollama daemon on ``localhost`` (default ``qwen2.5:3b``), so demos produce real
grounded prose with **no API key and no external egress** — the air-gap is preserved.
This is the realistic stand-in for the production internal SLM (``SlmGateway``); the
only difference is the wire format (Ollama's ``/api/chat``).

``httpx`` is imported lazily. ``num_ctx`` is set explicitly because Ollama otherwise
defaults to a 2048-token window, which would silently truncate the assembled
grounded context the generator depends on.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from app.core.config import AISettings
from app.domain.ports.llm_gateway import GenerationRequest, GenerationResult

# Match the SLM's binding constraint so the context assembler budgets identically
# whichever local provider is active.
_CONTEXT_WINDOW = 8192


class OllamaGateway:
    def __init__(self, settings: AISettings) -> None:
        self._endpoint = settings.local_endpoint.rstrip("/")
        self._model = settings.local_model
        self._timeout = settings.request_timeout_seconds
        self._max_output_tokens = settings.local_max_output_tokens
        self._keep_alive = settings.local_keep_alive
        self._client: Any | None = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            import httpx  # lazy

            self._client = httpx.AsyncClient(base_url=self._endpoint, timeout=self._timeout)
        return self._client

    @property
    def model_id(self) -> str:
        return f"ollama:{self._model}"

    @property
    def context_window(self) -> int:
        return _CONTEXT_WINDOW

    def _payload(self, request: GenerationRequest, *, stream: bool) -> dict[str, Any]:
        return {
            "model": self._model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.prompt},
            ],
            "stream": stream,
            "keep_alive": self._keep_alive,  # keep the model resident → no reload between runs
            "options": {
                "temperature": request.temperature,
                "num_ctx": _CONTEXT_WINDOW,
                # Cap output so CPU-only generation stays fast (pipeline asks for 1024).
                "num_predict": min(request.max_output_tokens, self._max_output_tokens),
                "stop": list(request.stop),
            },
        }

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        client = self._ensure_client()
        response = await client.post("/api/chat", json=self._payload(request, stream=False))
        response.raise_for_status()
        body = response.json()
        return GenerationResult(
            text=body["message"]["content"],
            input_tokens=body.get("prompt_eval_count", 0),
            output_tokens=body.get("eval_count", 0),
            model_id=self.model_id,
        )

    async def stream(self, request: GenerationRequest) -> AsyncIterator[str]:
        client = self._ensure_client()
        async with client.stream(
            "POST", "/api/chat", json=self._payload(request, stream=True)
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                chunk = json.loads(line)
                piece = chunk.get("message", {}).get("content", "")
                if piece:
                    yield piece

    async def count_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)  # heuristic; Ollama exposes no cheap sync count
