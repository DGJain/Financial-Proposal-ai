#!/usr/bin/env python
"""Seed demo data into the catalog DB for live verification / a fresh environment.

Runs the **real** financial-ingestion pipeline (with an injected extractor so it
needs no PDF libraries) against the configured PostgreSQL, then records one
grounded generation event + its proposal and one refused event — exactly the
shape the analytics surface reads. Idempotent ingestion (content-hash) plus
unique run ids make it safe to re-run.

Usage (PostgreSQL reachable via POSTGRES_DSN):
    POSTGRES_DSN=postgresql+asyncpg://fpp:fpp@localhost:5432/fpp \
    ENVIRONMENT=local AIR_GAPPED=true \
    python infra/scripts/seed/seed_demo.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Make the backend package importable when run from anywhere.
_BACKEND = Path(__file__).resolve().parents[3] / "backend"
sys.path.insert(0, str(_BACKEND))

from app.container import Container  # noqa: E402
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
from app.modules.ingestion.pipeline.ingest_financial import (  # noqa: E402
    CallerContext,
    IngestFinancialDocument,
    IngestionRequest,
)

ENGAGEMENT = "eng-1"


class _FakeExtractor:
    def __init__(self, document: ExtractedDocument) -> None:
        self._document = document

    def supports(self, file_type: FileType) -> bool:
        return True

    async def extract(self, data: bytes, *, file_type: FileType) -> ExtractedDocument:
        return self._document


def _financial_doc() -> ExtractedDocument:
    body = (
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


async def main() -> None:
    os.environ.setdefault("ENVIRONMENT", "local")
    os.environ.setdefault("AIR_GAPPED", "true")
    if not os.environ.get("POSTGRES_DSN"):
        raise SystemExit("POSTGRES_DSN must be set to seed a real database.")

    container = Container()  # local AI adapters + real PostgreSQL UoW

    # 1) Real ingestion → documents + chunks + document_quality + (in-proc) vectors.
    ingest = IngestFinancialDocument(
        extractor=_FakeExtractor(_financial_doc()),
        object_store=container.object_store,
        embedder=container.embedder,
        vector_store=container.vector_store,
        human_review=container.human_review,
        uow_factory=container.unit_of_work,
    )
    result = await ingest.execute(
        IngestionRequest(
            data=b"%PDF-1.4 acme 2024",
            filename="acme-fy2024.pdf",
            file_type=FileType.PDF,
            caller=CallerContext(
                acl_groups=frozenset({"consultants"}),
                engagement_id=ENGAGEMENT,
                classification="confidential",
            ),
        )
    )
    doc_id = result.doc_id

    now = datetime.now(UTC)
    suffix = uuid.uuid4().hex[:8]
    gen_id = f"gen-demo-{suffix}"
    proposal_id = f"prop-demo-{suffix}"

    proposal = Proposal(
        proposal_id=proposal_id,
        gen_id=gen_id,
        engagement_id=ENGAGEMENT,
        template_id="tmpl-sow",
        versions=(
            ProposalVersion(
                version_no=1,
                sections=(
                    ProposalSection(
                        section_id=f"{proposal_id}-s1",
                        slot="overview",
                        heading="Engagement Overview",
                        order=0,
                        body="We propose a financial audit grounded in the FY2024 evidence.",
                    ),
                    ProposalSection(
                        section_id=f"{proposal_id}-s2",
                        slot="approach",
                        heading="Approach",
                        order=1,
                        body="A phased approach covering planning and fieldwork.",
                    ),
                ),
                created_ts=now,
                created_by="analyst-1",
                status=ProposalStatus.DRAFT,
            ),
        ),
        status=ProposalStatus.DRAFT,
    )

    generated = GenerationEvent(
        gen_id=gen_id,
        engagement_id=ENGAGEMENT,
        prompt="Audit services for Acme Corporation FY2024",
        ts=now,
        outcome=GenerationOutcome.GENERATED,
        confidence=0.84,
        confidence_band=ConfidenceBand.HIGH,
        retrieval_hits=(
            RetrievalHit(
                chunk_id=f"{doc_id}-c0000", doc_id=doc_id, repository=Repository.FINANCIAL,
                score=0.91, source_name="acme-fy2024.pdf", page_start=1, page_end=1,
            ),
            RetrievalHit(
                chunk_id="doc-prop-c0000", doc_id="doc-prop", repository=Repository.PROPOSAL,
                score=0.77, source_name="past_proposal.docx", page_start=1, page_end=2,
            ),
            RetrievalHit(
                chunk_id="doc-tmpl-c0000", doc_id="doc-tmpl", repository=Repository.TEMPLATE,
                score=0.80, source_name="sow_template.docx", page_start=1, page_end=1,
            ),
        ),
        citations=(
            Citation(
                claim_ordinal=1, chunk_id=f"{doc_id}-c0000", repository=Repository.FINANCIAL,
                source_name="acme-fy2024.pdf", page=1,
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

    refused = GenerationEvent(
        gen_id=f"gen-refused-{suffix}",
        engagement_id=ENGAGEMENT,
        prompt="Proposal for a wall-blocked engagement",
        ts=now - timedelta(days=1),
        outcome=GenerationOutcome.REFUSED,
        confidence=0.30,
        confidence_band=ConfidenceBand.LOW,
        refusal_reason="grounding below floor: no permitted financial evidence",
    )

    async with container.unit_of_work() as uow:
        await uow.proposals.add(proposal)
        await uow.audit.append(generated)
        await uow.audit.append(refused)
        await uow.commit()

    print("seeded:")
    print(f"  financial_doc_id = {doc_id} ({result.status.value})")
    print(f"  gen_id           = {gen_id}")
    print(f"  proposal_id      = {proposal_id}")
    print(f"  refused_gen_id   = gen-refused-{suffix}")


if __name__ == "__main__":
    asyncio.run(main())
