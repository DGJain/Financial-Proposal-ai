"""LLM-gateway factory — selects the provider from settings.

- ``ENVIRONMENT=local`` → ``EchoGateway`` (no server / no key needed).
- otherwise by ``AI_PROVIDER``: ``claude`` (prototype) or ``slm`` (production).

Production is additionally guarded at the settings layer (only ``slm`` is allowed),
so a misconfiguration fails closed before reaching here.
"""

from __future__ import annotations

from app.core.config import Environment, ModelProvider, Settings
from app.domain.ports.llm_gateway import LLMGatewayPort
from app.infrastructure.llm_gateway.claude.provider import ClaudeGateway
from app.infrastructure.llm_gateway.echo import EchoGateway
from app.infrastructure.llm_gateway.ollama.provider import OllamaGateway
from app.infrastructure.llm_gateway.slm.provider import SlmGateway


def make_llm_gateway(settings: Settings) -> LLMGatewayPort:
    if settings.environment is Environment.LOCAL:
        # DEV-ONLY local escape hatches for real prose instead of the echo placeholder.
        # Preferred: a local Ollama model — free, no key, no egress (air-gap intact),
        # the realistic stand-in for the production SLM. Alternatively Claude (an
        # outbound call, needs a key). Otherwise the deterministic EchoGateway.
        if settings.ai.dev_use_local:
            return OllamaGateway(settings.ai)
        if settings.ai.dev_use_claude and settings.ai.claude_api_key:
            return ClaudeGateway(settings.ai)
        return EchoGateway()
    if settings.ai.provider is ModelProvider.CLAUDE:
        return ClaudeGateway(settings.ai)
    return SlmGateway(settings.ai)
