"""Domain ports — abstract interfaces implemented by infrastructure adapters.

Dependencies point inward only (Clean Architecture DIP): use-cases depend on
these Protocols, adapters depend on the Protocols, and the domain depends on
nothing outside itself. This is what lets Claude↔SLM or ChromaDB↔X be swapped
without touching a single use-case.
"""

from app.domain.ports.audit_log import AuditLogPort
from app.domain.ports.chunk_catalog import ChunkCatalogPort
from app.domain.ports.document_catalog import DocumentCatalogPort
from app.domain.ports.embedder import EmbedderPort
from app.domain.ports.extractor import ExtractorPort
from app.domain.ports.human_review import HumanReviewQueuePort
from app.domain.ports.ingestion_lineage import IngestionLineagePort
from app.domain.ports.llm_gateway import (
    GenerationRequest,
    GenerationResult,
    LLMGatewayPort,
)
from app.domain.ports.object_store import ObjectStorePort
from app.domain.ports.proposal_repository import ProposalRepositoryPort
from app.domain.ports.unit_of_work import UnitOfWorkPort
from app.domain.ports.vector_store import (
    AclFilter,
    EmbeddedChunk,
    ScoredChunk,
    VectorStorePort,
    acl_filter_for,
    permits,
)

__all__ = [
    "AclFilter",
    "AuditLogPort",
    "ChunkCatalogPort",
    "DocumentCatalogPort",
    "EmbeddedChunk",
    "EmbedderPort",
    "ExtractorPort",
    "GenerationRequest",
    "GenerationResult",
    "HumanReviewQueuePort",
    "IngestionLineagePort",
    "LLMGatewayPort",
    "ObjectStorePort",
    "ProposalRepositoryPort",
    "ScoredChunk",
    "UnitOfWorkPort",
    "VectorStorePort",
    "acl_filter_for",
    "permits",
]
