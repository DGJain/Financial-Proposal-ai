"""Round-trip tests for the persistence adapters against in-memory SQLite.

Verifies the ports' contracts end-to-end: domain → ORM → DB → ORM → domain, plus
the append-only audit lineage reconstruction the Execution Report depends on.
A shared-connection StaticPool keeps the in-memory schema alive across sessions.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.domain.documents import (
    AccessControl,
    Document,
    FileType,
    Provenance,
    SensitivityFlag,
)
from app.domain.generation import (
    Citation,
    GateOutcome,
    GenerationEvent,
    GenerationGateVerdict,
    GenerationStage,
    RetrievalHit,
    StageTiming,
)
from app.domain.metrics import ContributionBreakdown, RepositoryShare
from app.domain.proposals import ConfidenceBand, GenerationOutcome
from app.domain.repositories import Repository, SoftDistribution
from app.infrastructure.persistence.postgres.base import Base
from app.infrastructure.persistence.postgres.models import (  # noqa: F401  (register tables)
    DocumentRow,
)
from app.infrastructure.persistence.postgres.unit_of_work import SqlAlchemyUnitOfWork


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


def _make_document() -> Document:
    return Document(
        doc_id="doc-1",
        repository=Repository.FINANCIAL,
        subtype="annual_report",
        provenance=Provenance(
            source_uri="s3://raw-originals/doc-1.pdf",
            file_type=FileType.PDF,
            ingestion_ts=datetime(2026, 6, 6, 12, 0, tzinfo=UTC),
            page_count=42,
            language="en",
            content_hash="sha256:abc123",
        ),
        access=AccessControl(
            acl_groups=frozenset({"deal-team-alpha", "analysts"}),
            engagement_id="eng-7",
            classification="confidential",
        ),
        soft_distribution=SoftDistribution(0.9, 0.07, 0.03),
        repo_confidence=0.9,
        sensitivity=frozenset({SensitivityFlag.MNPI}),
        lineage_root="audit:root:1",
    )


def _make_generation_event() -> GenerationEvent:
    return GenerationEvent(
        gen_id="gen-1",
        engagement_id="eng-7",
        prompt="Draft an investment advisory proposal for Acme Corp.",
        ts=datetime(2026, 6, 6, 12, 5, tzinfo=UTC),
        outcome=GenerationOutcome.GENERATED,
        confidence=0.84,
        confidence_band=ConfidenceBand.HIGH,
        retrieval_hits=(
            RetrievalHit("c-fin-1", "doc-1", Repository.FINANCIAL, 0.91, "Acme 10-K", 12, 13),
            RetrievalHit("c-prop-1", "doc-9", Repository.PROPOSAL, 0.72, "Past Proposal", 1, 2),
        ),
        citations=(
            Citation(0, "c-fin-1", Repository.FINANCIAL, "Acme 10-K", 12),
        ),
        stage_timings=(
            StageTiming(GenerationStage.RETRIEVE, 320),
            StageTiming(GenerationStage.GENERATE, 1800),
            StageTiming(GenerationStage.TOTAL, 2200),
        ),
        gate_outcomes=(
            GateOutcome("financial_grounding", GenerationGateVerdict.PASS),
            GateOutcome("factual_health", GenerationGateVerdict.PASS, "financial=100%"),
        ),
        contribution=ContributionBreakdown(
            context_share=RepositoryShare(60.0, 25.0, 15.0),
            factual_share=RepositoryShare(100.0, 0.0, 0.0),
        ),
        proposal_id="prop-1",
        policy_fingerprint="pol:v1",
        retrieval_weights={Repository.FINANCIAL: 0.6, Repository.PROPOSAL: 0.25},
    )


async def test_document_catalog_roundtrip(session_factory: async_sessionmaker) -> None:
    doc = _make_document()
    async with SqlAlchemyUnitOfWork(session_factory) as uow:
        await uow.documents.add(doc)
        await uow.commit()

    async with SqlAlchemyUnitOfWork(session_factory) as uow:
        loaded = await uow.documents.get("doc-1")
        assert loaded is not None
        assert loaded.repository is Repository.FINANCIAL
        assert loaded.access.acl_groups == doc.access.acl_groups
        assert loaded.access.engagement_id == "eng-7"
        assert loaded.soft_distribution.argmax is Repository.FINANCIAL
        assert loaded.sensitivity == {SensitivityFlag.MNPI}
        assert loaded.provenance.content_hash == "sha256:abc123"

        assert await uow.documents.exists_by_content_hash("sha256:abc123") is True
        assert await uow.documents.exists_by_content_hash("nope") is False
        assert await uow.documents.count_by_repository(Repository.FINANCIAL) == 1
        assert await uow.documents.count_by_repository(Repository.TEMPLATE) == 0


async def test_audit_log_roundtrip_reconstructs_report(
    session_factory: async_sessionmaker,
) -> None:
    event = _make_generation_event()
    async with SqlAlchemyUnitOfWork(session_factory) as uow:
        await uow.audit.append(event)
        await uow.commit()

    async with SqlAlchemyUnitOfWork(session_factory) as uow:
        loaded = await uow.audit.get("gen-1")
        assert loaded is not None
        assert loaded.outcome is GenerationOutcome.GENERATED
        assert len(loaded.retrieval_hits) == 2
        assert len(loaded.citations) == 1
        assert loaded.citations[0].repository is Repository.FINANCIAL
        assert loaded.total_duration_ms == 2200  # picks the TOTAL stage
        assert loaded.contribution is not None
        assert loaded.contribution.factual_share.financial == 100.0
        assert loaded.contribution.factual_health_ok(min_financial_factual_share_pct=99.9)
        assert loaded.retrieval_weights[Repository.FINANCIAL] == 0.6

        recent = await uow.audit.list_recent(limit=10)
        assert [e.gen_id for e in recent] == ["gen-1"]


async def test_refused_run_has_report_without_children(
    session_factory: async_sessionmaker,
) -> None:
    refused = GenerationEvent(
        gen_id="gen-refused",
        engagement_id="eng-7",
        prompt="Tell me Acme's revenue for a year we have no filings for.",
        ts=datetime(2026, 6, 6, 12, 10, tzinfo=UTC),
        outcome=GenerationOutcome.REFUSED,
        confidence=0.2,
        confidence_band=ConfidenceBand.LOW,
        refusal_reason="Financial grounding below floor after grounding loop.",
    )
    async with SqlAlchemyUnitOfWork(session_factory) as uow:
        await uow.audit.append(refused)
        await uow.commit()

    async with SqlAlchemyUnitOfWork(session_factory) as uow:
        loaded = await uow.audit.get("gen-refused")
        assert loaded is not None
        assert loaded.is_refused
        assert loaded.refusal_reason is not None
        assert loaded.retrieval_hits == ()
        assert loaded.citations == ()
        assert loaded.contribution is None
