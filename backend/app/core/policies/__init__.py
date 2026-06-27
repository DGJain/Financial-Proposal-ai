"""Centralized governance & tuning parameters.

Every research knob referenced across ingestion, RAG, and generation lives here
so it can be tuned in one place and recorded with the audit lineage for
reproducibility: classifier routing thresholds, loss-framework EQS weights and
per-repository gate predicates, and federated-retrieval branch/context budgets
and grounding floors.
"""

from app.core.policies.classifier import DEFAULT_CLASSIFIER_POLICY, ClassifierPolicy
from app.core.policies.quality_gates import (
    DEFAULT_QUALITY_GATE_POLICY,
    FinancialGatePredicate,
    Modality,
    ProposalGatePredicate,
    QualityGatePolicy,
    TemplateGatePredicate,
)
from app.core.policies.retrieval import (
    DEFAULT_RETRIEVAL_POLICY,
    BranchBudget,
    ContextBudget,
    GroundingPolicy,
    RetrievalPolicy,
)

__all__ = [
    "DEFAULT_CLASSIFIER_POLICY",
    "DEFAULT_QUALITY_GATE_POLICY",
    "DEFAULT_RETRIEVAL_POLICY",
    "BranchBudget",
    "ClassifierPolicy",
    "ContextBudget",
    "FinancialGatePredicate",
    "GroundingPolicy",
    "Modality",
    "ProposalGatePredicate",
    "QualityGatePolicy",
    "RetrievalPolicy",
    "TemplateGatePredicate",
]
