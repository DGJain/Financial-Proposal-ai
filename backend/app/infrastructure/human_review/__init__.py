"""Human-review queue adapters (the gate-failure / low-confidence sink)."""

from app.infrastructure.human_review.in_memory import InMemoryHumanReviewQueue

__all__ = ["InMemoryHumanReviewQueue"]
