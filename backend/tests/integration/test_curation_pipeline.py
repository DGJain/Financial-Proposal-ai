"""Phase 2 tests — three-repository ingestion + the curation/anonymization gate.

Exercises the repository-agnostic ``IngestionEngine`` and the ``CurateExemplar``
approval entry against real adapter logic with no servers (SQLite, in-memory
ChromaDB, deterministic embedder, fake extractor). Verifies: proposals/templates
ingest into their own collections with the right chunk shape and role; the
anonymization gate blocks exemplars that leak engagement content; open uploads
cannot reach the curated repositories; and per-repository quality gates
(Section Coverage, Placeholder Integrity) are enforced.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.domain.documents.enums import FileType
from app.domain.generation.enums import QualityGateVerdict
from app.domain.ingestion.enums import IngestionStatus, ReviewReason
from app.domain.ingestion.extracted import (
    ExtractedDocument,
    ExtractedPage,
    ExtractedTable,
    TextBlock,
)
from app.domain.repositories.repository import Repository, RoleInGeneration
from app.infrastructure.embedding.deterministic import DeterministicEmbedder
from app.infrastructure.human_review.in_memory import InMemoryHumanReviewQueue
from app.infrastructure.object_storage.in_memory import InMemoryObjectStore
from app.infrastructure.persistence.postgres.base import Base
from app.infrastructure.persistence.postgres.models import (  # noqa: F401  (register tables)
    DocumentQualityRow,
    DocumentRow,
)
from app.infrastructure.persistence.postgres.unit_of_work import SqlAlchemyUnitOfWork
from app.infrastructure.vector_store.chromadb.adapter import ChromaVectorStore
from app.infrastructure.vector_store.chromadb.in_memory import InMemoryChromaClient
from app.modules.ingestion.curation.curate import CurateExemplar
from app.modules.ingestion.pipeline.engine import (
    CallerContext,
    IngestionEngine,
    IngestionRequest,
)
from app.modules.ingestion.strategies import build_strategy_registry


class FakeExtractor:
    def __init__(self, document: ExtractedDocument) -> None:
        self._document = document

    def supports(self, file_type: FileType) -> bool:
        return True

    async def extract(self, data: bytes, *, file_type: FileType) -> ExtractedDocument:
        return self._document


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    await engine.dispose()


class Harness:
    """Shared stores + per-document engine/curation builders."""

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self.session_factory = session_factory
        self.embedder = DeterministicEmbedder()
        self.vector_store = ChromaVectorStore(InMemoryChromaClient())
        self.object_store = InMemoryObjectStore()
        self.human_review = InMemoryHumanReviewQueue()

    def engine(self, document: ExtractedDocument) -> IngestionEngine:
        return IngestionEngine(
            extractor=FakeExtractor(document),
            object_store=self.object_store,
            embedder=self.embedder,
            vector_store=self.vector_store,
            human_review=self.human_review,
            uow_factory=lambda: SqlAlchemyUnitOfWork(self.session_factory),
            strategies=build_strategy_registry(
                embedding_model_version=self.embedder.model_version
            ),
        )

    def curate(self, document: ExtractedDocument) -> CurateExemplar:
        return CurateExemplar(self.engine(document))


@pytest.fixture
def harness(session_factory: async_sessionmaker) -> Harness:
    return Harness(session_factory)


# --- document builders -------------------------------------------------------


def _page(*texts: str, tables: tuple[ExtractedTable, ...] = ()) -> ExtractedPage:
    return ExtractedPage(
        page_number=1,
        text_blocks=tuple(TextBlock(text=t) for t in texts),
        tables=tables,
    )


def _proposal_clean() -> ExtractedDocument:
    # A Statement of Work (expects approach + pricing + timeline), fully anonymized.
    return ExtractedDocument(
        file_type=FileType.DOCX,
        pages=(
            _page(
                "Statement of Work and Approach: [CLIENT] engaged us to deliver the program.",
                "Pricing: fees are structured as [FEE] per phase.",
                "Timeline: the engagement runs across phases over [DURATION].",
            ),
        ),
    )


def _proposal_leaky() -> ExtractedDocument:
    return ExtractedDocument(
        file_type=FileType.DOCX,
        pages=(
            _page(
                "Statement of Work and Approach for ClientCorp.",
                "Pricing: fees were $5,000,000 for the engagement.",
                "Timeline: delivered across phases.",
            ),
        ),
    )


def _proposal_missing_sections() -> ExtractedDocument:
    return ExtractedDocument(
        file_type=FileType.DOCX,
        pages=(_page("Statement of Work and Approach: [CLIENT] scope only, no pricing or timeline."),),
    )


def _template_clean() -> ExtractedDocument:
    return ExtractedDocument(
        file_type=FileType.DOCX,
        pages=(
            _page(
                "Executive Summary template.",
                "Dear {client_name}, we propose [SERVICE] for your firm.",
                "Pricing: the total fee is {fee_amount}.",
            ),
        ),
    )


def _template_malformed() -> ExtractedDocument:
    return ExtractedDocument(
        file_type=FileType.DOCX,
        pages=(_page("Proposal structure outline. Total: {amount} for {2024fiscal}."),),
    )


def _financial_clean() -> ExtractedDocument:
    table = ExtractedTable(
        table_id="p1-t0",
        rows=(("Segment", "Amount"), ("A", "100"), ("B", "150"), ("Total", "250")),
        caption="Income Statement",
        has_total_row=True,
    )
    return ExtractedDocument(
        file_type=FileType.PDF,
        pages=(_page("Annual Report fiscal year 2024. Revenue and net income.", tables=(table,)),),
    )


def _request(data: bytes, *, hints: dict[str, str] | None = None, known: frozenset[str] = frozenset()) -> IngestionRequest:
    return IngestionRequest(
        data=data,
        filename="doc.bin",
        file_type=FileType.DOCX,
        caller=CallerContext(acl_groups=frozenset({"consultants"}), engagement_id="eng-1"),
        metadata_hints=hints or {},
        known_identifiers=known,
    )


# --- proposal curation -------------------------------------------------------


async def test_curated_proposal_indexed_into_repo_proposals(harness: Harness) -> None:
    result = await harness.curate(_proposal_clean()).execute(
        _request(b"proposal-clean", hints={"outcome": "won", "industry": "banking"}),
        target=Repository.PROPOSAL,
    )

    assert result.status is IngestionStatus.INDEXED
    assert result.repository is Repository.PROPOSAL
    assert await harness.vector_store.count(Repository.PROPOSAL) == result.chunk_count
    assert await harness.vector_store.count(Repository.FINANCIAL) == 0

    async with SqlAlchemyUnitOfWork(harness.session_factory) as uow:
        doc = await uow.documents.get(result.doc_id)
        assert doc is not None and doc.repository is Repository.PROPOSAL
        chunks = await uow.chunks.list_by_document(result.doc_id)
        assert chunks and all(c.role_in_generation is RoleInGeneration.EXEMPLAR for c in chunks)
        # Section-semantic chunks are tagged with section_type and the outcome.
        assert any(c.metadata.get("section_type") for c in chunks)
        assert all(c.metadata.get("outcome") == "won" for c in chunks)


async def test_anonymization_failure_blocks_exemplar(harness: Harness) -> None:
    result = await harness.curate(_proposal_leaky()).execute(
        _request(b"proposal-leaky", known=frozenset({"ClientCorp"})),
        target=Repository.PROPOSAL,
    )

    assert result.status is IngestionStatus.ROUTED_TO_REVIEW
    assert result.review_reason is ReviewReason.ANONYMIZATION_FAILED
    # Never embedded or cataloged — leakage is blocked at the gate.
    assert await harness.vector_store.count(Repository.PROPOSAL) == 0
    assert await harness.human_review.count() == 1
    async with SqlAlchemyUnitOfWork(harness.session_factory) as uow:
        assert await uow.documents.get(result.doc_id) is None


async def test_proposal_missing_sections_fails_coverage_gate(harness: Harness) -> None:
    result = await harness.curate(_proposal_missing_sections()).execute(
        _request(b"proposal-thin"), target=Repository.PROPOSAL
    )
    assert result.status is IngestionStatus.ROUTED_TO_REVIEW
    assert result.review_reason is ReviewReason.QUALITY_GATE_FAILED
    assert await harness.vector_store.count(Repository.PROPOSAL) == 0


# --- template curation -------------------------------------------------------


async def test_curated_template_indexed_with_slots_verbatim(harness: Harness) -> None:
    result = await harness.curate(_template_clean()).execute(
        _request(b"template-clean"), target=Repository.TEMPLATE
    )

    assert result.status is IngestionStatus.INDEXED
    assert result.repository is Repository.TEMPLATE
    assert result.gate_verdict is QualityGateVerdict.APPROVED
    assert await harness.vector_store.count(Repository.TEMPLATE) == result.chunk_count

    async with SqlAlchemyUnitOfWork(harness.session_factory) as uow:
        chunks = await uow.chunks.list_by_document(result.doc_id)
        assert all(c.role_in_generation is RoleInGeneration.SCAFFOLD for c in chunks)
        # Placeholder markers preserved verbatim so the template stays fillable.
        assert any("{client_name}" in c.text for c in chunks)

        lineage = await uow.lineage.get(result.doc_id)
        assert lineage is not None
        assert lineage.quality.placeholder_integrity == 1.0
        assert lineage.repository is Repository.TEMPLATE


async def test_template_malformed_placeholder_fails_gate(harness: Harness) -> None:
    result = await harness.curate(_template_malformed()).execute(
        _request(b"template-bad"), target=Repository.TEMPLATE
    )
    assert result.status is IngestionStatus.ROUTED_TO_REVIEW
    assert result.gate_verdict is QualityGateVerdict.HUMAN_REVIEW
    assert await harness.vector_store.count(Repository.TEMPLATE) == 0


# --- governance --------------------------------------------------------------


async def test_open_upload_cannot_reach_proposal_repository(harness: Harness) -> None:
    # An open upload of clearly proposal-shaped content must NOT be indexed as an
    # exemplar — user uploads are financial-only.
    result = await harness.engine(_proposal_clean()).execute(_request(b"sneaky-proposal"))
    assert result.status is IngestionStatus.ROUTED_TO_REVIEW
    assert result.review_reason is ReviewReason.LOW_CLASSIFIER_CONFIDENCE
    assert await harness.vector_store.count(Repository.PROPOSAL) == 0


async def test_curation_rejects_financial_target(harness: Harness) -> None:
    with pytest.raises(ValueError, match="proposal or template"):
        await harness.curate(_financial_clean()).execute(
            _request(b"fin"), target=Repository.FINANCIAL
        )


# --- collection isolation across all three repositories ----------------------


async def test_three_repositories_are_isolated(harness: Harness) -> None:
    fin = await harness.engine(_financial_clean()).execute(
        IngestionRequest(b"fin-doc", "f.pdf", FileType.PDF, CallerContext())
    )
    prop = await harness.curate(_proposal_clean()).execute(
        _request(b"prop-doc"), target=Repository.PROPOSAL
    )
    tmpl = await harness.curate(_template_clean()).execute(
        _request(b"tmpl-doc"), target=Repository.TEMPLATE
    )

    assert fin.status is prop.status is tmpl.status is IngestionStatus.INDEXED
    # Each repository's vectors live only in its own collection.
    assert await harness.vector_store.count(Repository.FINANCIAL) == fin.chunk_count
    assert await harness.vector_store.count(Repository.PROPOSAL) == prop.chunk_count
    assert await harness.vector_store.count(Repository.TEMPLATE) == tmpl.chunk_count

    async with SqlAlchemyUnitOfWork(harness.session_factory) as uow:
        assert await uow.documents.count_by_repository(Repository.FINANCIAL) == 1
        assert await uow.documents.count_by_repository(Repository.PROPOSAL) == 1
        assert await uow.documents.count_by_repository(Repository.TEMPLATE) == 1
