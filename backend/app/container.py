"""Composition root — the single place where ports are bound to adapters.

This is the wiring diagram for the whole backend. Nothing else constructs
infrastructure; use-cases receive ports through here (Dependency Inversion). It
also encodes the local-dev story: when ``ENVIRONMENT=local`` every external
dependency is satisfied by an in-process implementation (in-memory object store,
deterministic embedder, in-memory vector store, echo gateway), so the platform
runs with **no servers and no secrets** — while production wiring is one enum away.

PostgreSQL is always real (run via docker-compose locally) because the Unit of
Work and Alembic migrations are exercised as-is. Adapters are built lazily and
cached so importing the app (e.g. for ``/health``) touches nothing heavy.
"""

from __future__ import annotations

from functools import cached_property

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Environment, Settings, get_settings
from app.domain.repositories.repository import Repository
from app.domain.ports.embedder import EmbedderPort
from app.domain.ports.extractor import ExtractorPort
from app.domain.ports.human_review import HumanReviewQueuePort
from app.domain.ports.llm_gateway import LLMGatewayPort
from app.domain.ports.object_store import ObjectStorePort
from app.domain.ports.vector_store import VectorStorePort
from app.infrastructure.embedding.deterministic import DeterministicEmbedder
from app.infrastructure.embedding.http_embedder import HttpEmbedder
from app.infrastructure.extraction.composite import CompositeExtractor
from app.infrastructure.human_review.in_memory import InMemoryHumanReviewQueue
from app.infrastructure.llm_gateway.factory import make_llm_gateway
from app.infrastructure.object_storage.in_memory import InMemoryObjectStore
from app.infrastructure.object_storage.s3 import S3ObjectStore
from app.infrastructure.persistence.postgres.unit_of_work import SqlAlchemyUnitOfWork
from app.infrastructure.vector_store.chromadb.adapter import ChromaVectorStore
from app.infrastructure.vector_store.chromadb.client import make_chroma_client
from app.infrastructure.vector_store.chromadb.in_memory import InMemoryChromaClient
from app.modules.ingestion.curation.curate import CurateExemplar
from app.modules.ingestion.pipeline.engine import IngestionEngine
from app.modules.ingestion.pipeline.ingest_financial import IngestFinancialDocument
from app.modules.ingestion.strategies import build_strategy_registry
from app.modules.metrics.generation_health.health import GenerationHealth
from app.modules.metrics.repository_stats.stats import RepositoryMetrics
from app.modules.proposal_generation.export.export import ExportProposal
from app.modules.proposal_generation.graph.orchestrator import GenerateProposal
from app.modules.proposal_generation.intake.brief_extractor import BriefExtractor
from app.modules.proposal_generation.versioning.edit import EditProposal
from app.modules.reporting.execution_report import BuildExecutionReport
from app.modules.reporting.history import ListPromptHistory


class Container:
    """Lazily builds and caches the adapter for each domain port."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        # Injectable so DB-backed use-cases can run against an in-memory SQLite
        # session in tests; ``None`` falls back to the real PostgreSQL factory.
        self._session_factory = session_factory

    @property
    def _is_local(self) -> bool:
        return self.settings.environment is Environment.LOCAL

    @cached_property
    def object_store(self) -> ObjectStorePort:
        if self._is_local:
            s = self.settings.object_storage
            return InMemoryObjectStore(s.bucket_raw, s.bucket_versioned)
        return S3ObjectStore(self.settings.object_storage)

    @cached_property
    def embedder(self) -> EmbedderPort:
        if self._is_local:
            return DeterministicEmbedder(model_version=self.settings.ai.embedding_model_version)
        return HttpEmbedder(self.settings.ai)

    @cached_property
    def vector_store(self) -> VectorStorePort:
        client = InMemoryChromaClient() if self._is_local else make_chroma_client()
        return ChromaVectorStore(client)

    @cached_property
    def llm_gateway(self) -> LLMGatewayPort:
        return make_llm_gateway(self.settings)

    @cached_property
    def extractor(self) -> ExtractorPort:
        """Format-dispatching extractor (each adapter lazy-imports its library)."""
        return CompositeExtractor()

    @cached_property
    def human_review(self) -> HumanReviewQueuePort:
        """Process-wide review queue (in-memory for Phase 1)."""
        return InMemoryHumanReviewQueue()

    def unit_of_work(self) -> SqlAlchemyUnitOfWork:
        """A fresh Unit of Work per use-case invocation (not cached)."""
        return SqlAlchemyUnitOfWork(self._session_factory)

    # --- readiness probes (K8s) ----------------------------------------------

    async def ping_database(self) -> None:
        """Round-trip the catalog DB — raises if PostgreSQL is unreachable."""
        from app.infrastructure.persistence.postgres.engine import get_session_factory

        factory = self._session_factory or get_session_factory()
        async with factory() as session:
            await session.execute(text("SELECT 1"))

    async def ping_vector_store(self) -> None:
        """Touch the vector store — raises if ChromaDB is unreachable.

        In ``local`` this hits the in-process client (always up); against a real
        ChromaDB it confirms the collection endpoint answers.
        """
        await self.vector_store.count(Repository.FINANCIAL)

    @cached_property
    def ingestion_engine(self) -> IngestionEngine:
        """The repository-agnostic engine, wired to the bound ports + strategies."""
        return IngestionEngine(
            extractor=self.extractor,
            object_store=self.object_store,
            embedder=self.embedder,
            vector_store=self.vector_store,
            human_review=self.human_review,
            uow_factory=self.unit_of_work,
            strategies=build_strategy_registry(
                embedding_model_version=self.embedder.model_version
            ),
        )

    def ingest_financial(self) -> IngestFinancialDocument:
        """Open-upload entry — user uploads into ``repo_financial`` only."""
        return IngestFinancialDocument(
            extractor=self.extractor,
            object_store=self.object_store,
            embedder=self.embedder,
            vector_store=self.vector_store,
            human_review=self.human_review,
            uow_factory=self.unit_of_work,
        )

    def curate_exemplar(self) -> CurateExemplar:
        """Curation/approval entry — proposal/template into their gated repos."""
        return CurateExemplar(self.ingestion_engine)

    def brief_extractor(self) -> BriefExtractor:
        """Infer the structured brief (entity/year/type…) from the composer's query.

        Query-first intake: fills only the fields the caller left blank, so explicit
        Advanced-panel values always win. Bound to the same LLM gateway as
        generation (local Ollama in air-gapped dev), with a regex fallback."""
        return BriefExtractor(self.llm_gateway)

    def generate_proposal(self) -> GenerateProposal:
        """Phase 3 read/generate use-case — federated retrieval → grounded proposal.

        Bound to the same ports as ingestion (vector store, embedder, LLM gateway,
        Unit of Work) plus the default retrieval/context/grounding policy, which is
        recorded with every generation event for auditability."""
        return GenerateProposal(
            vector_store=self.vector_store,
            embedder=self.embedder,
            gateway=self.llm_gateway,
            uow_factory=self.unit_of_work,
        )

    def edit_proposal(self) -> EditProposal:
        """Text-only, structure-locked edit entry — appends a new ProposalVersion."""
        return EditProposal(uow_factory=self.unit_of_work)

    # --- Phase 5: read/analytics + export surface ----------------------------

    def execution_report(self) -> BuildExecutionReport:
        """Reconstruct one run's Execution Report from the audit log + quality."""
        return BuildExecutionReport(uow_factory=self.unit_of_work)

    def prompt_history(self) -> ListPromptHistory:
        """A page of prompt-history analytics rows (newest first)."""
        return ListPromptHistory(uow_factory=self.unit_of_work)

    def repository_metrics(self) -> RepositoryMetrics:
        """Repository composition cards + corpus contribution."""
        return RepositoryMetrics(uow_factory=self.unit_of_work)

    def generation_health(self) -> GenerationHealth:
        """Generation-health aggregates over a rolling window."""
        return GenerationHealth(uow_factory=self.unit_of_work)

    def export_proposal(self) -> ExportProposal:
        """Render the locked template + lineage and mark the proposal exported."""
        return ExportProposal(uow_factory=self.unit_of_work)


_container: Container | None = None


def get_container() -> Container:
    """Process-wide container (FastAPI dependency / startup wiring)."""
    global _container
    if _container is None:
        _container = Container()
    return _container
