"""Phase 5 tests — the analytics / reporting / export read surface.

Drives the FastAPI app through an in-process ASGI transport (single event loop, no
server) with the composition root overridden to a test ``Container`` backed by a
SQLite Unit of Work + in-memory ChromaDB. The seed is realistic: financial
documents are run through the **real** ingestion pipeline (so ``document_quality``
holds genuine OCR/EQS/information-loss), then generation events are recorded
against those documents' ids so the report/history quality-join exercises real
lineage. Verifies the Execution Report (10 sections + refusal), Prompt-History
rows, repository + generation-health metrics, and proposal export (markdown/HTML +
the information-loss gate).
"""

from __future__ import annotations

import os

os.environ.setdefault("ENVIRONMENT", "local")
os.environ.setdefault("AIR_GAPPED", "true")
os.environ.setdefault("POSTGRES_DSN", "postgresql+asyncpg://u:p@localhost:5432/fpp")
os.environ.setdefault("REDIS_DSN", "redis://localhost:6379/0")

from collections.abc import AsyncIterator  # noqa: E402
from datetime import UTC, datetime, timedelta  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.container import Container, get_container  # noqa: E402
from app.domain.documents.enums import FileType  # noqa: E402
from app.domain.generation.enums import GenerationGateVerdict, GenerationStage  # noqa: E402
from app.domain.generation.generation_event import (  # noqa: E402
    Citation,
    GateOutcome,
    GenerationEvent,
    RetrievalHit,
    StageTiming,
)
from app.domain.ingestion.extracted import (  # noqa: E402
    ExtractedDocument,
    ExtractedPage,
    ExtractedTable,
    TextBlock,
)
from app.domain.ingestion.lineage import IngestionLineage  # noqa: E402
from app.domain.metrics.contribution import ContributionBreakdown, RepositoryShare  # noqa: E402
from app.domain.proposals.enums import (  # noqa: E402
    ConfidenceBand,
    GenerationOutcome,
    ProposalStatus,
)
from app.domain.proposals.proposal import (  # noqa: E402
    Proposal,
    ProposalSection,
    ProposalVersion,
)
from app.domain.repositories.repository import Repository  # noqa: E402
from app.infrastructure.persistence.postgres.base import Base  # noqa: E402
from app.infrastructure.persistence.postgres.models import (  # noqa: E402,F401  (register tables)
    DocumentQualityRow,
    DocumentRow,
    GenerationEventRow,
    ProposalRow,
)
from app.infrastructure.persistence.postgres.unit_of_work import (  # noqa: E402
    SqlAlchemyUnitOfWork,
)
from app.main import create_app  # noqa: E402
from app.modules.ingestion.pipeline.ingest_financial import (  # noqa: E402
    CallerContext,
    IngestFinancialDocument,
    IngestionRequest,
)
from app.modules.proposal_generation.export.export import (  # noqa: E402
    ExportBlockedError,
    ExportProposal,
    ExportProposalCommand,
)

ENGAGEMENT = "eng-1"


# --- fakes & fixtures --------------------------------------------------------


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


def _financial_doc(year: int, issuer: str) -> ExtractedDocument:
    body = (
        f"{issuer} Annual Report fiscal year {year}. "
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


def _ingest(container: Container, doc: ExtractedDocument, filename: str) -> IngestFinancialDocument:
    return IngestFinancialDocument(
        extractor=FakeExtractor(doc),
        object_store=container.object_store,
        embedder=container.embedder,
        vector_store=container.vector_store,
        human_review=container.human_review,
        uow_factory=container.unit_of_work,
    )


def _request(data: bytes, filename: str) -> IngestionRequest:
    return IngestionRequest(
        data=data,
        filename=filename,
        file_type=FileType.PDF,
        caller=CallerContext(
            acl_groups=frozenset({"consultants"}),
            engagement_id=ENGAGEMENT,
            classification="confidential",
        ),
    )


def _generated_event(
    gen_id: str,
    *,
    prompt: str,
    ts: datetime,
    financial_doc: tuple[str, str],  # (doc_id, source_name)
    proposal_id: str,
) -> GenerationEvent:
    fin_doc_id, fin_source = financial_doc
    return GenerationEvent(
        gen_id=gen_id,
        engagement_id=ENGAGEMENT,
        prompt=prompt,
        ts=ts,
        outcome=GenerationOutcome.GENERATED,
        confidence=0.84,
        confidence_band=ConfidenceBand.HIGH,
        retrieval_hits=(
            RetrievalHit(
                chunk_id=f"{fin_doc_id}-c0000",
                doc_id=fin_doc_id,
                repository=Repository.FINANCIAL,
                score=0.91,
                source_name=fin_source,
                page_start=1,
                page_end=1,
            ),
            RetrievalHit(
                chunk_id="doc-prop-c0000",
                doc_id="doc-prop",
                repository=Repository.PROPOSAL,
                score=0.77,
                source_name="past_proposal.docx",
                page_start=1,
                page_end=2,
            ),
            RetrievalHit(
                chunk_id="doc-tmpl-c0000",
                doc_id="doc-tmpl",
                repository=Repository.TEMPLATE,
                score=0.80,
                source_name="sow_template.docx",
                page_start=1,
                page_end=1,
            ),
        ),
        citations=(
            Citation(
                claim_ordinal=1,
                chunk_id=f"{fin_doc_id}-c0000",
                repository=Repository.FINANCIAL,
                source_name=fin_source,
                page=1,
            ),
        ),
        stage_timings=(
            StageTiming(stage=GenerationStage.REWRITE, duration_ms=12),
            StageTiming(stage=GenerationStage.RETRIEVE, duration_ms=40),
            StageTiming(stage=GenerationStage.GROUND, duration_ms=8),
            StageTiming(stage=GenerationStage.GENERATE, duration_ms=140),
            StageTiming(stage=GenerationStage.TOTAL, duration_ms=200),
        ),
        gate_outcomes=(
            GateOutcome(name="financial_grounding", verdict=GenerationGateVerdict.PASS),
        ),
        contribution=ContributionBreakdown(
            context_share=RepositoryShare(financial=60.0, proposal=30.0, template=10.0),
            factual_share=RepositoryShare(financial=100.0, proposal=0.0, template=0.0),
        ),
        proposal_id=proposal_id,
    )


def _refused_event(gen_id: str, *, ts: datetime) -> GenerationEvent:
    return GenerationEvent(
        gen_id=gen_id,
        engagement_id=ENGAGEMENT,
        prompt="Audit services for a wall-blocked engagement",
        ts=ts,
        outcome=GenerationOutcome.REFUSED,
        confidence=0.30,
        confidence_band=ConfidenceBand.LOW,
        refusal_reason="grounding below floor: no permitted financial evidence",
    )


def _proposal(proposal_id: str, gen_id: str, ts: datetime) -> Proposal:
    version = ProposalVersion(
        version_no=1,
        sections=(
            ProposalSection(
                section_id=f"{proposal_id}-s1",
                slot="overview",
                heading="Engagement Overview",
                order=0,
                body="We propose a financial audit grounded in the FY evidence.",
            ),
            ProposalSection(
                section_id=f"{proposal_id}-s2",
                slot="approach",
                heading="Approach",
                order=1,
                body="A phased approach covering planning and fieldwork.",
            ),
        ),
        created_ts=ts,
        created_by="analyst-1",
        status=ProposalStatus.DRAFT,
    )
    return Proposal(
        proposal_id=proposal_id,
        gen_id=gen_id,
        engagement_id=ENGAGEMENT,
        template_id="tmpl-sow",
        versions=(version,),
        status=ProposalStatus.DRAFT,
    )


class Seed:
    """What the seed produced, so assertions can reference the real ids/quality."""

    def __init__(self) -> None:
        self.fin_doc_id: str = ""
        self.fin_source: str = ""
        self.fin_quality: IngestionLineage | None = None
        self.gen_id: str = "gen-0001"
        self.refused_gen_id: str = "gen-0002"
        self.proposal_id: str = "prop-0001"


async def _seed(container: Container) -> Seed:
    seed = Seed()
    now = datetime.now(UTC)

    # 1) Real ingestion → real document_quality + chunks + vector store.
    result = await _ingest(container, _financial_doc(2024, "Acme Corporation"), "acme.pdf").execute(
        _request(b"%PDF-1.4 acme 2024", "acme.pdf")
    )
    seed.fin_doc_id = result.doc_id
    seed.fin_source = "acme.pdf"

    # 2) Record a generated run against that document, a refused run, and a proposal.
    async with SqlAlchemyUnitOfWork(container._session_factory) as uow:  # type: ignore[attr-defined]
        seed.fin_quality = await uow.lineage.get(result.doc_id)
        await uow.proposals.add(_proposal(seed.proposal_id, seed.gen_id, now))
        await uow.audit.append(
            _generated_event(
                seed.gen_id,
                prompt="Audit services for Acme Corporation FY2024",
                ts=now,
                financial_doc=(seed.fin_doc_id, seed.fin_source),
                proposal_id=seed.proposal_id,
            )
        )
        await uow.audit.append(_refused_event(seed.refused_gen_id, ts=now - timedelta(days=2)))
        await uow.commit()
    return seed


@pytest_asyncio.fixture
async def seeded(
    session_factory: async_sessionmaker,
) -> AsyncIterator[tuple[httpx.AsyncClient, Container, Seed]]:
    container = Container(session_factory=session_factory)
    seed = await _seed(container)
    app = create_app()
    app.dependency_overrides[get_container] = lambda: container
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, container, seed


# --- Execution Report (§6.6) -------------------------------------------------


async def test_report_reconstructs_run(seeded: tuple[httpx.AsyncClient, Container, Seed]) -> None:
    client, _, seed = seeded
    response = await client.get(f"/report/{seed.gen_id}")
    assert response.status_code == 200
    body = response.json()

    assert body["prompt"] == "Audit services for Acme Corporation FY2024"  # §1
    assert body["outcome"] == "generated"
    assert seed.fin_source in body["files_used"]  # §2
    # §3 financial docs carry scores; §4/§5 the other repositories.
    assert [h["doc_id"] for h in body["retrieved_financial"]] == [seed.fin_doc_id]
    assert body["retrieved_financial"][0]["score"] == pytest.approx(0.91)
    assert body["retrieved_proposal"] and body["retrieved_template"]
    # §6/7/8 quality joined from the *real* ingestion lineage.
    assert seed.fin_quality is not None
    assert body["quality"]["ocr_confidence"] == pytest.approx(seed.fin_quality.quality.ocr_confidence, abs=1e-4)
    assert body["quality"]["extraction_quality"] == pytest.approx(seed.fin_quality.quality.eqs, abs=1e-4)
    assert body["quality"]["gate_verdict"] == "approved"
    assert body["quality"]["document_count"] == 1
    # §9 timeline sums to the headline; §10 citations resolve to financial.
    assert body["total_duration_ms"] == 200
    assert {s["stage"] for s in body["stages"]} == {"rewrite", "retrieve", "ground", "generate", "total"}
    assert body["citations"][0]["source_name"] == seed.fin_source
    assert body["contribution"]["factual_share"]["financial"] == 100.0


async def test_report_unknown_returns_404(seeded: tuple[httpx.AsyncClient, Container, Seed]) -> None:
    client, _, _ = seeded
    assert (await client.get("/report/gen-nope")).status_code == 404


async def test_refused_run_still_reports(seeded: tuple[httpx.AsyncClient, Container, Seed]) -> None:
    client, _, seed = seeded
    body = (await client.get(f"/report/{seed.refused_gen_id}")).json()
    assert body["outcome"] == "refused"
    assert body["refusal_reason"]
    assert body["retrieved_financial"] == []
    assert body["quality"] is None
    assert body["stages"] == []
    assert body["citations"] == []


# --- Prompt History (§5.A) ---------------------------------------------------


async def test_history_rows_carry_analytics_fields(
    seeded: tuple[httpx.AsyncClient, Container, Seed],
) -> None:
    client, _, seed = seeded
    body = (await client.get("/history?limit=50")).json()
    rows = {r["gen_id"]: r for r in body["rows"]}
    assert set(rows) == {seed.gen_id, seed.refused_gen_id}

    generated = rows[seed.gen_id]
    assert generated["title"] == "Audit services for Acme Corporation FY2024"
    assert generated["proposal_id"] == seed.proposal_id
    assert generated["files_used"] == 3  # distinct retrieved doc ids
    assert generated["outcome"] == "generated"
    assert generated["processing_time_s"] == pytest.approx(0.2)
    assert generated["ocr_confidence"] is not None
    assert generated["repository_contribution_pct"] == pytest.approx(60.0)

    refused = rows[seed.refused_gen_id]
    assert refused["outcome"] == "refused"
    assert refused["ocr_confidence"] is None
    assert refused["extraction_quality"] is None
    assert refused["repository_contribution_pct"] == 0.0


async def test_history_is_newest_first(seeded: tuple[httpx.AsyncClient, Container, Seed]) -> None:
    client, _, seed = seeded
    rows = (await client.get("/history")).json()["rows"]
    assert rows[0]["gen_id"] == seed.gen_id  # most recent ts


# --- Repository metrics (§6.7) -----------------------------------------------


async def test_repository_metrics(seeded: tuple[httpx.AsyncClient, Container, Seed]) -> None:
    client, _, _ = seeded
    body = (await client.get("/metrics/repository")).json()
    assert body["financial_documents"] == 1
    assert body["proposal_examples"] == 0
    assert body["templates"] == 0
    assert body["embedded_chunks"] > 0
    assert body["last_ingestion_ts"] is not None
    # Only financial chunks were ingested → corpus is 100% financial.
    assert body["corpus_contribution"]["financial"] == 100.0


# --- Generation health (Page 4 §2) -------------------------------------------


async def test_generation_health(seeded: tuple[httpx.AsyncClient, Container, Seed]) -> None:
    client, _, _ = seeded
    body = (await client.get("/metrics/generation-health?days=7")).json()
    assert body["window_days"] == 7
    assert body["runs_total"] == 2
    assert body["proposals_generated"] == 1
    assert body["refusal_rate"] == pytest.approx(0.5)
    assert 0.0 < body["avg_confidence"] < 1.0
    assert len(body["daily"]) == 7  # one bar per day in the window
    assert sum(b["generated"] + b["refused"] for b in body["daily"]) == 2
    assert {b["label"] for b in body["info_loss_distribution"]} == {"low", "medium", "high"}
    # The single generated run's evidence is high quality → counted once.
    assert sum(b["count"] for b in body["info_loss_distribution"]) == 1


# --- Export (§6.4) -----------------------------------------------------------


async def test_export_markdown_marks_exported(
    seeded: tuple[httpx.AsyncClient, Container, Seed],
) -> None:
    client, _, seed = seeded
    response = await client.get(f"/proposals/{seed.proposal_id}/export?format=markdown")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    text = response.text
    assert "Engagement Overview" in text  # locked template heading
    assert "Lineage & Provenance" not in text  # metrics live in the report, not the doc
    assert seed.fin_source in text  # citation source (Sources endnotes)

    # Lifecycle advanced to EXPORTED.
    after = (await client.get(f"/proposals/{seed.proposal_id}")).json()
    assert after["status"] == "exported"


async def test_export_pdf_and_docx(seeded: tuple[httpx.AsyncClient, Container, Seed]) -> None:
    client, _, seed = seeded
    pdf = await client.get(f"/proposals/{seed.proposal_id}/export?format=pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"].startswith("application/pdf")
    assert pdf.content[:4] == b"%PDF"  # real PDF magic bytes

    docx = await client.get(f"/proposals/{seed.proposal_id}/export?format=docx")
    assert docx.status_code == 200
    assert "wordprocessingml" in docx.headers["content-type"]
    assert docx.content[:2] == b"PK"  # .docx is a zip container


async def test_export_html(seeded: tuple[httpx.AsyncClient, Container, Seed]) -> None:
    client, _, seed = seeded
    response = await client.get(f"/proposals/{seed.proposal_id}/export?format=html")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<!DOCTYPE html>" in response.text


async def test_get_document_returns_editable_html(
    seeded: tuple[httpx.AsyncClient, Container, Seed],
) -> None:
    client, _, seed = seeded
    response = await client.get(f"/proposals/{seed.proposal_id}/document")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    text = response.text
    assert '<div class="doc">' in text  # the editable document body
    assert "Engagement Overview" in text  # locked template heading
    assert "Lineage & Provenance" not in text  # no metrics in the client doc


async def test_export_edited_html_to_pdf_and_docx(
    seeded: tuple[httpx.AsyncClient, Container, Seed],
) -> None:
    """The editor posts its current HTML; export converts *that*, not the stored draft."""
    client, _, seed = seeded
    edited = (
        '<div class="doc"><h1 class="title">My Edited Title</h1>'
        '<section class="sec"><h2><span class="num">1.</span> Overview</h2>'
        "<div class=\"body\"><p>Hand-edited prose for the client.</p></div></section></div>"
    )
    pdf = await client.post(
        f"/proposals/{seed.proposal_id}/export?format=pdf", json={"html": edited}
    )
    assert pdf.status_code == 200
    assert pdf.headers["content-type"].startswith("application/pdf")
    assert pdf.content[:4] == b"%PDF"

    docx = await client.post(
        f"/proposals/{seed.proposal_id}/export?format=docx", json={"html": edited}
    )
    assert docx.status_code == 200
    assert "wordprocessingml" in docx.headers["content-type"]
    assert docx.content[:2] == b"PK"


async def test_export_missing_returns_404(seeded: tuple[httpx.AsyncClient, Container, Seed]) -> None:
    client, _, _ = seeded
    assert (await client.get("/proposals/prop-nope/export")).status_code == 404


async def test_export_blocked_by_information_loss_gate(
    seeded: tuple[httpx.AsyncClient, Container, Seed],
) -> None:
    # A zero-tolerance ceiling blocks export when the run drew on financial
    # evidence with any measurable information loss.
    _, container, seed = seeded
    use_case = ExportProposal(
        uow_factory=container.unit_of_work, max_information_loss_pct=-1.0
    )
    with pytest.raises(ExportBlockedError):
        await use_case.execute(ExportProposalCommand(proposal_id=seed.proposal_id))
