"""Federated, role-aware retrieval fan-out."""

from app.modules.rag.retrievers.federated import CandidatePool, FederatedRetriever

__all__ = ["CandidatePool", "FederatedRetriever"]
