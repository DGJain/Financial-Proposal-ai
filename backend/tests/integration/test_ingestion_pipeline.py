"""End-to-end tests for the Phase 1 financial ingestion vertical slice.

Exercises ``IngestFinancialDocument`` against the real adapters' logic with no
servers: SQLite (via ``SqlAlchemyUnitOfWork``), the in-memory ChromaDB client +
``ChromaVectorStore``, the ``DeterministicEmbedder``, the in-memory object store
and review queue, and a hand-built fake extractor that stands in for PyMuPDF/OCR
(tests inject fakes directly, per the Phase 1 handoff).

Covers the six acceptance criteria: full pipeline → ``repo_financial`` + catalog;
gate failures routed to review (never indexed); ACL enforced on retrieval;
idempotent re-upload; π_d / confidence / quality / redaction recorded to lineage.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.domain.documents.enums import FileType, SensitivityFlag
from app.domain.generation.enums import QualityGateVerdict
from app.domain.ingestion.enums import IngestionStatus, ReviewReason
from app.domain.ingestion.extracted import (
    ExtractedDocument,
    ExtractedPage,
    ExtractedTable,
    TextBlock,
)
from app.domain.ports.vector_store import AclFilter
from app.domain.repositories.repository import Repository
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
from app.modules.ingestion.pipeline.ingest_financial import (
    CallerContext,
    IngestFinancialDocument,
    IngestionRequest,
)


# --- fakes & fixtures --------------------------------------------------------


class FakeExtractor:
    """Returns a pre-built ``ExtractedDocument``, standing in for the real libs."""

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


class PipelineHarness:
    """Bundles shared infra so a test can ingest and then inspect every store."""

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self.session_factory = session_factory
        self.embedder = DeterministicEmbedder()
        self.vector_store = ChromaVectorStore(InMemoryChromaClient())
        self.object_store = InMemoryObjectStore()
        self.human_review = InMemoryHumanReviewQueue()

    def use_case(self, document: ExtractedDocument) -> IngestFinancialDocument:
        return IngestFinancialDocument(
            extractor=FakeExtractor(document),
            object_store=self.object_store,
            embedder=self.embedder,
            vector_store=self.vector_store,
            human_review=self.human_review,
            uow_factory=lambda: SqlAlchemyUnitOfWork(self.session_factory),
        )


@pytest.fixture
def harness(session_factory: async_sessionmaker) -> PipelineHarness:
    return PipelineHarness(session_factory)


# --- document builders -------------------------------------------------------


def _clean_financial_doc(*, text: str | None = None) -> ExtractedDocument:
    body = text or (
        "Acme Corporation Annual Report fiscal year 2024. "
        "Total revenue grew and net income improved. Total assets increased."
    )
    table = ExtractedTable(
        table_id="p1-t0",
        rows=(("Segment", "Amount"), ("Product A", "100"), ("Product B", "150"), ("Total", "250")),
        caption="Income Statement",
        has_total_row=True,
    )
    page = ExtractedPage(page_number=1, text_blocks=(TextBlock(text=body),), tables=(table,))
    return ExtractedDocument(file_type=FileType.PDF, pages=(page,))


def _scanned_low_confidence_doc() -> ExtractedDocument:
    # Financial content (so the classifier routes financial) but a numeric table
    # extracted by low-confidence OCR → critical low-confidence region.
    table = ExtractedTable(
        table_id="p1-t0",
        rows=(("Line", "Amount"), ("Cash", "900"), ("Total", "900")),
        caption="Balance Sheet",
        has_total_row=True,
        ocr_confidence=0.55,
    )
    block = TextBlock(
        text="Annual Report fiscal year 2023 revenue net income total assets.",
        is_ocr=True,
        ocr_confidence=0.55,
    )
    page = ExtractedPage(page_number=1, text_blocks=(block,), tables=(table,), is_scanned=True)
    return ExtractedDocument(file_type=FileType.PNG, pages=(page,))


def _redaction_doc() -> ExtractedDocument:
    body = (
        "Acme Corporation Annual Report fiscal year 2023. "
        "Contact john.doe@example.com regarding MNPI details. "
        "Total revenue was $5,000,000 and net income rose."
    )
    page = ExtractedPage(page_number=1, text_blocks=(TextBlock(text=body),))
    return ExtractedDocument(file_type=FileType.PDF, pages=(page,))


def _proposal_doc() -> ExtractedDocument:
    body = (
        "This proposal outlines our engagement scope, deliverables, methodology, "
        "timeline and approach for the client. See the case study and pitch."
    )
    page = ExtractedPage(page_number=1, text_blocks=(TextBlock(text=body),))
    return ExtractedDocument(file_type=FileType.DOCX, pages=(page,))


def _request(data: bytes = b"%PDF-1.4 raw bytes") -> IngestionRequest:
    return IngestionRequest(
        data=data,
        filename="acme.pdf",
        file_type=FileType.PDF,
        caller=CallerContext(
            acl_groups=frozenset({"analysts"}),
            engagement_id="eng-7",
            classification="confidential",
        ),
    )


# --- 1) full pipeline → repo_financial + catalog -----------------------------


async def test_clean_financial_document_is_indexed(harness: PipelineHarness) -> None:
    result = await harness.use_case(_clean_financial_doc()).execute(_request())

    assert result.status is IngestionStatus.INDEXED
    assert result.gate_verdict is QualityGateVerdict.APPROVED
    assert result.chunk_count > 0

    # Embedded chunks landed in repo_financial (and only there).
    assert await harness.vector_store.count(Repository.FINANCIAL) == result.chunk_count
    assert await harness.vector_store.count(Repository.PROPOSAL) == 0

    async with SqlAlchemyUnitOfWork(harness.session_factory) as uow:
        doc = await uow.documents.get(result.doc_id)
        assert doc is not None
        assert doc.repository is Repository.FINANCIAL
        chunks = await uow.chunks.list_by_document(result.doc_id)
        assert len(chunks) == result.chunk_count
        assert all(c.vector_id is not None for c in chunks)
        # A table is kept atomic as its own chunk.
        assert any(c.metadata.get("content_type") == "table" for c in chunks)


# --- 2) gate failure routes to review, never indexed -------------------------


async def test_quality_gate_failure_routes_to_review(harness: PipelineHarness) -> None:
    result = await harness.use_case(_scanned_low_confidence_doc()).execute(_request())

    assert result.status is IngestionStatus.ROUTED_TO_REVIEW
    assert result.review_reason is ReviewReason.QUALITY_GATE_FAILED
    assert result.gate_verdict is QualityGateVerdict.HUMAN_REVIEW

    # Nothing was embedded or cataloged.
    assert await harness.vector_store.count(Repository.FINANCIAL) == 0
    assert await harness.human_review.count() == 1
    async with SqlAlchemyUnitOfWork(harness.session_factory) as uow:
        assert await uow.documents.get(result.doc_id) is None


async def test_low_classifier_confidence_routes_to_review(harness: PipelineHarness) -> None:
    result = await harness.use_case(_proposal_doc()).execute(_request())

    assert result.status is IngestionStatus.ROUTED_TO_REVIEW
    assert result.review_reason is ReviewReason.LOW_CLASSIFIER_CONFIDENCE
    assert await harness.vector_store.count(Repository.FINANCIAL) == 0


# --- 3) ACL enforced on retrieval --------------------------------------------


async def test_acl_is_enforced_on_retrieval(harness: PipelineHarness) -> None:
    await harness.use_case(_clean_financial_doc()).execute(_request())
    query = await harness.embedder.embed_query("revenue and net income")

    permitted = AclFilter(caller_groups=frozenset({"analysts"}), caller_engagement_id="eng-7")
    blocked_engagement = AclFilter(caller_groups=frozenset({"analysts"}), caller_engagement_id="eng-9")
    blocked_group = AclFilter(caller_groups=frozenset({"outsiders"}), caller_engagement_id="eng-7")

    assert len(await harness.vector_store.query(Repository.FINANCIAL, query, k=10, acl=permitted)) > 0
    assert await harness.vector_store.query(Repository.FINANCIAL, query, k=10, acl=blocked_engagement) == []
    assert await harness.vector_store.query(Repository.FINANCIAL, query, k=10, acl=blocked_group) == []


# --- 4) idempotent re-upload -------------------------------------------------


async def test_reingesting_same_bytes_is_idempotent(harness: PipelineHarness) -> None:
    use_case = harness.use_case(_clean_financial_doc())
    first = await use_case.execute(_request())
    count_after_first = await harness.vector_store.count(Repository.FINANCIAL)

    second = await use_case.execute(_request())

    assert second.status is IngestionStatus.SKIPPED_DUPLICATE
    assert second.doc_id == first.doc_id
    assert await harness.vector_store.count(Repository.FINANCIAL) == count_after_first
    async with SqlAlchemyUnitOfWork(harness.session_factory) as uow:
        assert await uow.documents.count_by_repository(Repository.FINANCIAL) == 1


# --- 5) π_d, confidence, quality, redaction recorded to lineage --------------


async def test_lineage_records_classification_quality_and_redaction(harness: PipelineHarness) -> None:
    result = await harness.use_case(_redaction_doc()).execute(_request())
    assert result.status is IngestionStatus.INDEXED

    async with SqlAlchemyUnitOfWork(harness.session_factory) as uow:
        lineage = await uow.lineage.get(result.doc_id)
        assert lineage is not None
        # π_d is a real distribution summing to 1, financial dominant.
        pi = lineage.soft_distribution
        assert pi.argmax is Repository.FINANCIAL
        assert abs(pi.financial + pi.proposal + pi.template - 1.0) < 1e-6
        assert lineage.classification_confidence == pi.confidence
        # Quality scores recorded.
        assert lineage.quality.eqs >= 0.90
        assert lineage.gate_verdict is QualityGateVerdict.APPROVED
        # Redaction recorded: the email (PII) and MNPI marker, with a ledger ref —
        # but the $5,000,000 figure was preserved (never redacted).
        assert lineage.redaction_counts.get("pii") == 1
        assert lineage.redaction_counts.get("mnpi") == 1
        assert lineage.redaction_ledger_uri is not None
        assert lineage.sensitivity == {SensitivityFlag.PII, SensitivityFlag.MNPI}
        assert lineage.policy_fingerprint is not None

        doc = await uow.documents.get(result.doc_id)
        assert doc is not None
        assert doc.sensitivity == {SensitivityFlag.PII, SensitivityFlag.MNPI}

    # The preserved figure survived into an indexed chunk; the email did not.
    async with SqlAlchemyUnitOfWork(harness.session_factory) as uow:
        chunks = await uow.chunks.list_by_document(result.doc_id)
    all_text = " ".join(c.text for c in chunks)
    assert "5,000,000" in all_text
    assert "john.doe@example.com" not in all_text
    assert "[REDACTED:PII]" in all_text
