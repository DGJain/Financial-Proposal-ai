"""Phase 3 tests — federated retrieval → grounded proposal generation.

Exercises the ``GenerateProposal`` orchestrator end-to-end against real adapter
logic with **no servers** (SQLite, in-memory ChromaDB, deterministic embedder,
Echo gateway). The three repositories are seeded directly into the vector store,
then a brief drives the full pipeline. Verifies the dissertation's core
invariants:

* retrieval fans out to all three collections **concurrently**, ACL-pre-filtered;
* ranking is **within-repo** (wrong-period evidence is dropped, not down-weighted);
* **every citation resolves to ``repo_financial``** — exemplar/template "facts"
  never become citations;
* the **financial grounding gate** refuses when evidence is absent (still
  persisting a replayable ``GenerationEvent``);
* the **factual-health guardrail** blocks & refuses on figure leakage;
* a clean run persists both the ``GenerationEvent`` lineage and the ``Proposal``,
  with contribution metrics recorded.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.domain.chunks.chunk import Chunk, ChunkSpan
from app.domain.documents.acl import AccessControl
from app.domain.generation.brief import (
    BriefAttachment,
    GenerationBrief,
    RequesterContext,
)
from app.domain.ports.llm_gateway import GenerationRequest, GenerationResult
from app.domain.ports.vector_store import EmbeddedChunk
from app.domain.proposals.enums import ConfidenceBand, GenerationOutcome
from app.domain.repositories.repository import (
    Repository,
    RoleInGeneration,
    role_of,
)
from app.infrastructure.embedding.deterministic import DeterministicEmbedder
from app.infrastructure.llm_gateway.echo import EchoGateway
from app.infrastructure.persistence.postgres.base import Base
from app.infrastructure.persistence.postgres.models import (  # noqa: F401  (register tables)
    GenerationEventRow,
    ProposalRow,
)
from app.infrastructure.persistence.postgres.unit_of_work import SqlAlchemyUnitOfWork
from app.infrastructure.vector_store.chromadb.adapter import ChromaVectorStore
from app.infrastructure.vector_store.chromadb.in_memory import InMemoryChromaClient
from app.modules.proposal_generation.graph.orchestrator import (
    GenerateProposal,
    GenerateProposalCommand,
)

ENGAGEMENT = "eng-1"
GROUPS = frozenset({"consultants"})


# --- fixtures ----------------------------------------------------------------


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


class ConcurrencyProbe:
    """Wraps a vector store to record the peak number of in-flight queries."""

    def __init__(self, inner: ChromaVectorStore) -> None:
        self._inner = inner
        self._in_flight = 0
        self.peak = 0

    async def query(self, *args: Any, **kwargs: Any):
        self._in_flight += 1
        self.peak = max(self.peak, self._in_flight)
        await asyncio.sleep(0)  # yield so concurrent branches interleave
        try:
            return await self._inner.query(*args, **kwargs)
        finally:
            self._in_flight -= 1

    def __getattr__(self, name: str) -> Any:  # delegate upsert/count/etc.
        return getattr(self._inner, name)


class FigureLeakGateway:
    """A gateway that emits a figure present only in an exemplar — simulating a
    model that lifts a past client's number into a new proposal."""

    def __init__(self, leaked_figure: str) -> None:
        self._leaked = leaked_figure

    @property
    def model_id(self) -> str:
        return "figure-leak-test"

    @property
    def context_window(self) -> int:
        return 8192

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        text = f"We propose a fee of {self._leaked} for the engagement."
        return GenerationResult(
            text=text,
            input_tokens=await self.count_tokens(request.prompt),
            output_tokens=await self.count_tokens(text),
            model_id=self.model_id,
        )

    async def stream(self, request: GenerationRequest) -> AsyncIterator[str]:
        yield (await self.generate(request)).text

    async def count_tokens(self, text: str) -> int:
        return len(text.split())


class Harness:
    def __init__(self, session_factory: async_sessionmaker, *, gateway=None) -> None:
        self.session_factory = session_factory
        self.embedder = DeterministicEmbedder()
        self.store = ChromaVectorStore(InMemoryChromaClient())
        self.gateway = gateway or EchoGateway()

    async def seed(self, repository: Repository, chunks: Sequence[Chunk]) -> None:
        embeddings = await self.embedder.embed_documents([c.text for c in chunks])
        await self.store.upsert(
            repository,
            [EmbeddedChunk(chunk=c, embedding=e) for c, e in zip(chunks, embeddings)],
        )

    def orchestrator(self, *, vector_store=None) -> GenerateProposal:
        return GenerateProposal(
            vector_store=vector_store or self.store,
            embedder=self.embedder,
            gateway=self.gateway,
            uow_factory=lambda: SqlAlchemyUnitOfWork(self.session_factory),
        )


@pytest.fixture
def harness(session_factory: async_sessionmaker) -> Harness:
    return Harness(session_factory)


# --- chunk builders ----------------------------------------------------------


def _access() -> AccessControl:
    return AccessControl(acl_groups=GROUPS, engagement_id=ENGAGEMENT)


def _chunk(
    repository: Repository,
    doc_id: str,
    ordinal: int,
    text: str,
    metadata: dict[str, Any],
    *,
    access: AccessControl | None = None,
) -> Chunk:
    return Chunk(
        chunk_id=f"{doc_id}-c{ordinal:04d}",
        doc_id=doc_id,
        repository=repository,
        role_in_generation=role_of(repository),
        text=text,
        ordinal=ordinal,
        span=ChunkSpan(page_start=1, page_end=1),
        access=access or _access(),
        embedding_model_version="deterministic-hash-v1",
        metadata=metadata,
    )


def _financial_tight(doc_id: str = "doc-fin-tight", year: int = 2024) -> Chunk:
    return _chunk(
        Repository.FINANCIAL, doc_id, 0,
        "Acme Corp fiscal year 2024 revenue net income. Annual report for Acme Corp. "
        "Revenue and net income for fiscal year 2024.",
        {"fiscal_year": year, "issuer": "Acme Corp", "subtype": "annual_report"},
    )


def _financial_figures(doc_id: str = "doc-fin-figs", year: int = 2024) -> Chunk:
    return _chunk(
        Repository.FINANCIAL, doc_id, 0,
        "Acme Corp fiscal year 2024 annual report. Revenue was $1,200,000 and net "
        "income was $300,000 for fiscal year 2024.",
        {"fiscal_year": year, "issuer": "Acme Corp", "subtype": "annual_report"},
    )


def _exemplar(doc_id: str = "doc-prop", *, figure: str | None = None) -> Chunk:
    base = (
        "Statement of work and approach for a banking engagement. We structure the "
        "program in phases with clear deliverables."
    )
    if figure:
        base += f" Our fee was {figure} for that prior engagement."
    return _chunk(
        Repository.PROPOSAL, doc_id, 0, base,
        {"outcome": "won", "subtype": "past_proposal", "section_type": "approach"},
    )


def _template(doc_id: str = "doc-tmpl") -> Chunk:
    return _chunk(
        Repository.TEMPLATE, doc_id, 0,
        "Statement of Work\nApproach: {approach}. Fees: {fee_amount}. Timeline: {timeline}.",
        {"status": "approved", "subtype": "statement_of_work", "slot_count": 3},
    )


def _brief() -> GenerationBrief:
    return GenerationBrief(
        title="Audit services for Acme",
        proposal_type="statement_of_work",
        entity="Acme Corp",
        fiscal_year=2024,
        sector="banking",
        line_items=("revenue", "net income"),
    )


def _requester(engagement_id: str = ENGAGEMENT) -> RequesterContext:
    return RequesterContext(
        engagement_id=engagement_id, caller_groups=GROUPS, requested_by="analyst-1"
    )


async def _seed_all(harness: Harness) -> None:
    await harness.seed(Repository.FINANCIAL, [_financial_tight(), _financial_figures()])
    await harness.seed(Repository.PROPOSAL, [_exemplar()])
    await harness.seed(Repository.TEMPLATE, [_template()])


# --- tests -------------------------------------------------------------------


async def test_full_pipeline_generates_grounded_proposal(harness: Harness) -> None:
    await _seed_all(harness)
    result = await harness.orchestrator().execute(
        GenerateProposalCommand(brief=_brief(), requester=_requester())
    )

    assert result.outcome is GenerationOutcome.GENERATED
    assert result.confidence_band in {ConfidenceBand.HIGH, ConfidenceBand.MEDIUM}
    assert result.proposal is not None

    event = result.event
    # Every citation resolves to the financial (evidence) repository.
    assert event.citations
    assert all(c.repository is Repository.FINANCIAL for c in event.citations)
    # Fan-out reached all three collections.
    repos_hit = {h.repository for h in event.retrieval_hits}
    assert repos_hit == {Repository.FINANCIAL, Repository.PROPOSAL, Repository.TEMPLATE}

    # Contribution recorded: financial carries all factual weight; context is shared.
    assert event.contribution is not None
    assert event.contribution.factual_share.financial == 100.0
    assert event.contribution.context_share.financial > 0.0
    assert event.contribution.context_share.template > 0.0

    # Both the lineage event and the proposal persisted and are replayable.
    async with SqlAlchemyUnitOfWork(harness.session_factory) as uow:
        stored_event = await uow.audit.get(event.gen_id)
        assert stored_event is not None and stored_event.outcome is GenerationOutcome.GENERATED
        stored_proposal = await uow.proposals.get(result.proposal.proposal_id)
        assert stored_proposal is not None
        # Structure is bound to the template scaffold (locked sections).
        assert stored_proposal.current_version.sections
        assert all(s.slot for s in stored_proposal.current_version.sections)


async def test_multi_section_template_yields_one_section_per_heading(harness: Harness) -> None:
    # A single template document with numbered headings defines the whole structure;
    # the assembler splits it into one locked section per heading, in order, with the
    # leading number stripped (the exporter numbers sections itself).
    multi = _chunk(
        Repository.TEMPLATE, "doc-tmpl-multi", 0,
        "Company Proposal Template\n"
        "1. Executive Summary\nState the recommendation.\n"
        "2. Market Opportunity\nDescribe the opportunity.\n"
        "3. Recommendation\nState the next steps.",
        {"status": "approved", "subtype": "statement_of_work", "slot_count": 3},
    )
    await harness.seed(Repository.FINANCIAL, [_financial_tight(), _financial_figures()])
    await harness.seed(Repository.PROPOSAL, [_exemplar()])
    await harness.seed(Repository.TEMPLATE, [multi])

    result = await harness.orchestrator().execute(
        GenerateProposalCommand(brief=_brief(), requester=_requester())
    )
    assert result.proposal is not None
    sections = sorted(result.proposal.current_version.sections, key=lambda s: s.order)
    assert [s.heading for s in sections] == [
        "Executive Summary",
        "Market Opportunity",
        "Recommendation",
    ]


async def test_retrieval_fans_out_concurrently(harness: Harness) -> None:
    await _seed_all(harness)
    probe = ConcurrencyProbe(harness.store)
    await harness.orchestrator(vector_store=probe).execute(
        GenerateProposalCommand(brief=_brief(), requester=_requester())
    )
    # All three branches were in flight at once (asyncio.gather fan-out).
    assert probe.peak >= 2


async def test_wrong_engagement_retrieves_nothing_and_refuses(harness: Harness) -> None:
    await _seed_all(harness)
    result = await harness.orchestrator().execute(
        GenerateProposalCommand(brief=_brief(), requester=_requester(engagement_id="eng-OTHER"))
    )
    # ACL wall: a caller in the wrong engagement sees no evidence → refuse.
    assert result.outcome is GenerationOutcome.REFUSED
    assert result.proposal is None
    assert result.event.citations == ()
    assert result.event.refusal_reason
    # Refused runs still persist a replayable Execution Report.
    async with SqlAlchemyUnitOfWork(harness.session_factory) as uow:
        assert await uow.audit.get(result.event.gen_id) is not None


async def test_no_evidence_falls_back_to_style_only(harness: Harness) -> None:
    # Exemplar + template present, but NO financial evidence. A beautiful template
    # still cannot produce a *cited* proposal — but instead of refusing outright the
    # platform emits a figure-free STYLE-ONLY draft styled on the template/exemplars
    # (zero citations, LOW confidence). The anti-hallucination guarantee holds
    # because the draft asserts no figures at all.
    from app.domain.generation.enums import GenerationGateVerdict

    await harness.seed(Repository.PROPOSAL, [_exemplar()])
    await harness.seed(Repository.TEMPLATE, [_template()])
    result = await harness.orchestrator().execute(
        GenerateProposalCommand(brief=_brief(), requester=_requester())
    )
    assert result.outcome is GenerationOutcome.STYLE_ONLY
    assert result.proposal is not None
    # No financial evidence → no citations, and grounding gates the band to LOW.
    assert result.event.citations == ()
    assert result.confidence_band is ConfidenceBand.LOW
    # Lineage records the below-floor grounding plus a clean numeric verification.
    verdicts = {g.name: g.verdict for g in result.event.gate_outcomes}
    assert verdicts["financial_grounding"] is GenerationGateVerdict.REFUSE
    assert verdicts["numeric_verification"] is GenerationGateVerdict.PASS
    # The style-only draft and its lineage persist and are replayable.
    async with SqlAlchemyUnitOfWork(harness.session_factory) as uow:
        stored = await uow.audit.get(result.event.gen_id)
        assert stored is not None and stored.outcome is GenerationOutcome.STYLE_ONLY
        assert await uow.proposals.get(result.proposal.proposal_id) is not None


async def test_no_evidence_and_nothing_to_style_on_refuses(harness: Harness) -> None:
    # Nothing seeded anywhere: no evidence to ground AND no template/exemplar to
    # style on → there is nothing to produce, so the run still refuses.
    result = await harness.orchestrator().execute(
        GenerateProposalCommand(brief=_brief(), requester=_requester())
    )
    assert result.outcome is GenerationOutcome.REFUSED
    assert result.proposal is None
    assert "grounding" in result.event.refusal_reason
    # The grounding gate decision is recorded in lineage.
    assert any(g.name == "financial_grounding" for g in result.event.gate_outcomes)


async def test_wrong_period_evidence_dropped_not_cited(harness: Harness) -> None:
    # A 2023 chunk and a 2024 chunk for the same issuer; the brief asks for 2024.
    await harness.seed(
        Repository.FINANCIAL,
        [_financial_tight("doc-fy2024", 2024), _financial_tight("doc-fy2023", 2023)],
    )
    await harness.seed(Repository.PROPOSAL, [_exemplar()])
    await harness.seed(Repository.TEMPLATE, [_template()])
    result = await harness.orchestrator().execute(
        GenerateProposalCommand(brief=_brief(), requester=_requester())
    )
    assert result.outcome is GenerationOutcome.GENERATED
    cited_docs = {c.chunk_id.rsplit("-c", 1)[0] for c in result.event.citations}
    # The 2023 evidence was retrieved into the pool but dropped at ranking — never cited.
    retrieved_docs = {h.doc_id for h in result.event.retrieval_hits}
    assert "doc-fy2023" in retrieved_docs
    assert "doc-fy2023" not in cited_docs
    assert cited_docs == {"doc-fy2024"}


class ContentGateway:
    """Returns fixed Markdown so the attachment-driven content path can be asserted."""

    def __init__(self, text: str) -> None:
        self._text = text

    @property
    def model_id(self) -> str:
        return "content-test"

    @property
    def context_window(self) -> int:
        return 8192

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        return GenerationResult(
            text=self._text,
            input_tokens=await self.count_tokens(request.prompt),
            output_tokens=await self.count_tokens(self._text),
            model_id=self.model_id,
        )

    async def stream(self, request: GenerationRequest) -> AsyncIterator[str]:
        yield (await self.generate(request)).text

    async def count_tokens(self, text: str) -> int:
        return len(text.split())


_ATTACHMENT_MATERIAL = (
    "FY2025 Key Performance Metrics\n\n"
    "Metric | FY2025\n"
    "Active Customers | 1,704\n"
    "Headcount | 401\n"
)


def _brief_with_attachment(text: str = _ATTACHMENT_MATERIAL) -> GenerationBrief:
    return GenerationBrief(
        title="Proposal for Northwind Logistics",
        proposal_type="advisory",
        entity="Northwind Logistics",
        attachments=(BriefAttachment(name="metrics.pdf", text=text),),
    )


async def test_attachment_drives_dynamic_sections_and_keeps_client_table(
    session_factory: async_sessionmaker,
) -> None:
    # The caller attached client material with a data table. No financial evidence is
    # seeded (Northwind isn't in the corpus), so this is ungrounded — but because an
    # attachment is present, the platform weaves it into a dynamically-sectioned
    # proposal and reproduces the client's table verbatim. A client-supplied figure
    # ("1,704", which the numeric gate would otherwise flag) is allowed through.
    from app.domain.generation.enums import GenerationGateVerdict

    narrative = (
        "## Executive Summary\n"
        "Northwind served 1,704 active customers in FY2025, a strong base.\n\n"
        "## Operational Outlook\n"
        "Headcount supports continued growth.\n"
    )
    harness = Harness(session_factory, gateway=ContentGateway(narrative))
    await harness.seed(Repository.PROPOSAL, [_exemplar()])
    await harness.seed(Repository.TEMPLATE, [_template()])

    result = await harness.orchestrator().execute(
        GenerateProposalCommand(brief=_brief_with_attachment(), requester=_requester())
    )

    assert result.outcome is GenerationOutcome.GENERATED
    assert result.proposal is not None
    sections = sorted(result.proposal.current_version.sections, key=lambda s: s.order)
    headings = [s.heading for s in sections]
    # Dynamic section count (not fixed to 3) driven by the model's headings, PLUS the
    # deterministic verbatim data section.
    assert "Executive Summary" in headings
    assert "Operational Outlook" in headings
    # The reproduced data section keeps the client's OWN caption from the doc,
    # not a generic "Client-Supplied Data" label.
    assert "FY2025 Key Performance Metrics" in headings
    assert "Client-Supplied Data" not in headings
    assert any(s.slot == "data" for s in sections)
    # The client's table figures are reproduced verbatim in the data section.
    data_section = next(s for s in sections if s.slot == "data")
    assert "1,704" in data_section.body and "401" in data_section.body
    # The client-supplied figure passed the numeric gate (allowed, unverified); no
    # invented figure, so the run is GENERATED with zero citations (nothing grounded).
    verdicts = {g.name: g.verdict for g in result.event.gate_outcomes}
    assert verdicts["numeric_verification"] is GenerationGateVerdict.PASS
    assert "client_supplied_content" in verdicts
    assert result.event.citations == ()
    async with SqlAlchemyUnitOfWork(harness.session_factory) as uow:
        assert await uow.proposals.get(result.proposal.proposal_id) is not None


async def test_attachment_path_still_blocks_invented_figure(
    session_factory: async_sessionmaker,
) -> None:
    # Even on the attachment path, a figure that is in NEITHER the attachment NOR cited
    # evidence is invented → blocked & refused. The no-fabrication guarantee holds.
    from app.domain.generation.enums import GenerationGateVerdict

    narrative = "## Summary\nWe propose an engagement fee of $5,000,000.\n"
    harness = Harness(session_factory, gateway=ContentGateway(narrative))
    await harness.seed(Repository.PROPOSAL, [_exemplar()])
    await harness.seed(Repository.TEMPLATE, [_template()])

    result = await harness.orchestrator().execute(
        GenerateProposalCommand(brief=_brief_with_attachment(), requester=_requester())
    )

    assert result.outcome is GenerationOutcome.REFUSED
    assert result.proposal is None
    verdicts = {g.name: g.verdict for g in result.event.gate_outcomes}
    assert verdicts["numeric_verification"] is GenerationGateVerdict.BLOCK_REGENERATE


async def test_figure_leakage_blocks_and_refuses(session_factory: async_sessionmaker) -> None:
    leaked = "$5,000,000"
    harness = Harness(session_factory, gateway=FigureLeakGateway(leaked))
    # Strong financial grounding so we reach generation, plus an exemplar that
    # carries the leaking figure (a past client's fee).
    await harness.seed(Repository.FINANCIAL, [_financial_tight(), _financial_figures()])
    await harness.seed(Repository.PROPOSAL, [_exemplar(figure=leaked)])
    await harness.seed(Repository.TEMPLATE, [_template()])

    result = await harness.orchestrator().execute(
        GenerateProposalCommand(brief=_brief(), requester=_requester())
    )

    # The exemplar's figure leaked into the output → block & regenerate → refuse.
    assert result.outcome is GenerationOutcome.REFUSED
    assert result.proposal is None
    verdicts = {g.name: g.verdict for g in result.event.gate_outcomes}
    from app.domain.generation.enums import GenerationGateVerdict

    assert verdicts["numeric_verification"] is GenerationGateVerdict.BLOCK_REGENERATE
    assert verdicts["factual_health"] is GenerationGateVerdict.BLOCK_REGENERATE
    # Factual health: financial no longer carries ~100% of factual weight.
    assert result.event.contribution.factual_share.financial < 100.0
    async with SqlAlchemyUnitOfWork(harness.session_factory) as uow:
        assert await uow.audit.get(result.event.gen_id) is not None
