"""Per-repository ingestion strategies + the registry the engine dispatches on.

One ``RepositoryIngestionStrategy`` per repository bundles its assessor, gate,
metadata extractor and chunker. ``build_strategy_registry`` wires all three for a
given embedding-model version and quality policy; the engine looks a strategy up
by the classifier's routed ``Repository`` (open/closed — adding a repository is a
new strategy here, not an engine change).
"""

from __future__ import annotations

from app.core.policies.quality_gates import (
    DEFAULT_QUALITY_GATE_POLICY,
    QualityGatePolicy,
)
from app.domain.repositories.repository import Repository
from app.modules.ingestion.contracts import RepositoryIngestionStrategy
from app.modules.ingestion.strategies.financial import FinancialStrategy
from app.modules.ingestion.strategies.proposal import ProposalStrategy
from app.modules.ingestion.strategies.template import TemplateStrategy


def build_strategy_registry(
    *,
    embedding_model_version: str,
    policy: QualityGatePolicy = DEFAULT_QUALITY_GATE_POLICY,
) -> dict[Repository, RepositoryIngestionStrategy]:
    """Build the repository → strategy map for one embedder + policy snapshot."""
    return {
        Repository.FINANCIAL: FinancialStrategy(embedding_model_version, policy),
        Repository.PROPOSAL: ProposalStrategy(embedding_model_version, policy),
        Repository.TEMPLATE: TemplateStrategy(embedding_model_version, policy),
    }


__all__ = [
    "FinancialStrategy",
    "ProposalStrategy",
    "TemplateStrategy",
    "build_strategy_registry",
]
