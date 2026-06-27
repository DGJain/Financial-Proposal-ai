"""Generation guardrails — factual-contribution health check."""

from app.modules.proposal_generation.guardrails.factual_health import (
    GATE_NAME,
    FactualHealthGuard,
)

__all__ = ["GATE_NAME", "FactualHealthGuard"]
