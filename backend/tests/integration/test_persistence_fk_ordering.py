"""Regression: parent rows must be flushed before their FK children.

The default SQLite test engine has foreign-key enforcement OFF, so an
out-of-order INSERT (e.g. ``document_quality`` before its parent ``documents``)
goes unnoticed there but fails on PostgreSQL, which enforces FKs at flush time.
This test pins the unit-of-work insert order by enabling ``PRAGMA foreign_keys=ON``
and running the real ingestion pipeline end to end — it must commit cleanly.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.domain.documents.enums import FileType
from app.domain.ingestion.enums import IngestionStatus
from app.domain.ingestion.extracted import (
    ExtractedDocument,
    ExtractedPage,
    ExtractedTable,
    TextBlock,
)
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


@pytest_asyncio.fixture
async def fk_enforcing_session_factory() -> AsyncIterator[async_sessionmaker]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_fk(dbapi_connection, _record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    await engine.dispose()


def _financial_doc() -> ExtractedDocument:
    body = (
        "Acme Corporation Annual Report fiscal year 2024. "
        "Total revenue grew and net income improved. Total assets increased."
    )
    table = ExtractedTable(
        table_id="p1-t0",
        rows=(("Segment", "Amount"), ("Product A", "100"), ("Total", "100")),
        caption="Income Statement",
        has_total_row=True,
    )
    page = ExtractedPage(page_number=1, text_blocks=(TextBlock(text=body),), tables=(table,))
    return ExtractedDocument(file_type=FileType.PDF, pages=(page,))


class _FakeExtractor:
    def __init__(self, document: ExtractedDocument) -> None:
        self._document = document

    def supports(self, file_type: FileType) -> bool:
        return True

    async def extract(self, data: bytes, *, file_type: FileType) -> ExtractedDocument:
        return self._document


async def test_ingestion_commits_with_foreign_keys_enforced(
    fk_enforcing_session_factory: async_sessionmaker,
) -> None:
    use_case = IngestFinancialDocument(
        extractor=_FakeExtractor(_financial_doc()),
        object_store=InMemoryObjectStore(),
        embedder=DeterministicEmbedder(),
        vector_store=ChromaVectorStore(InMemoryChromaClient()),
        human_review=InMemoryHumanReviewQueue(),
        uow_factory=lambda: SqlAlchemyUnitOfWork(fk_enforcing_session_factory),
    )

    # With FK enforcement on, this raises IntegrityError if documents/chunks/
    # document_quality are flushed out of dependency order.
    result = await use_case.execute(
        IngestionRequest(
            data=b"%PDF-1.4 acme",
            filename="acme.pdf",
            file_type=FileType.PDF,
            caller=CallerContext(
                acl_groups=frozenset({"analysts"}),
                engagement_id="eng-7",
                classification="confidential",
            ),
        )
    )
    assert result.status is IngestionStatus.INDEXED

    async with SqlAlchemyUnitOfWork(fk_enforcing_session_factory) as uow:
        lineage = await uow.lineage.get(result.doc_id)
        assert lineage is not None  # the FK child persisted alongside its parent
