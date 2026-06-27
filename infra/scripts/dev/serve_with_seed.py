#!/usr/bin/env python
"""Dev convenience: serve the API with demo evidence seeded IN-PROCESS.

In ``local`` the vector store is an in-process, per-process in-memory ChromaDB, so
data seeded by a separate script is invisible to a separately-launched server —
which is why a plain ``uvicorn`` refuses every generation (no evidence to ground
on). This launcher seeds the singleton container's vector store with one financial
evidence chunk, one approved template scaffold, and one won proposal exemplar
(ACL = the UI defaults eng-1 / consultants), then serves that same container — so
``POST /generate`` actually grounds and produces a cited proposal.

NOT for production. Run from the repo root:
    POSTGRES_DSN=postgresql+asyncpg://fpp:fpp@localhost:5432/fpp \
    REDIS_DSN=redis://localhost:6379/0 AIR_GAPPED=true ENVIRONMENT=local \
    python infra/scripts/dev/serve_with_seed.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[3] / "backend"
sys.path.insert(0, str(_BACKEND))

import uvicorn  # noqa: E402

from app.container import get_container  # noqa: E402
from app.domain.chunks.chunk import Chunk, ChunkSpan  # noqa: E402
from app.domain.documents.acl import AccessControl  # noqa: E402
from app.domain.ports.vector_store import EmbeddedChunk  # noqa: E402
from app.domain.repositories.repository import Repository, role_of  # noqa: E402
from app.main import create_app  # noqa: E402

ENGAGEMENT = "eng-1"
GROUPS = frozenset({"consultants"})

# Reuse the doc id that seed_demo.py ingests into PostgreSQL (deterministic from
# its content) so a generated proposal's citation resolves to a document that
# already has quality/lineage rows — the Execution Report then shows OCR /
# extraction / information-loss too. If it ever drifts, the report simply shows
# "—" for those fields; generation is unaffected.
FINANCIAL_DOC_ID = "doc-f41d87bd97e58332"


def _access() -> AccessControl:
    return AccessControl(acl_groups=GROUPS, engagement_id=ENGAGEMENT)


def _chunk(repository: Repository, doc_id: str, text: str, metadata: dict) -> Chunk:
    return Chunk(
        chunk_id=f"{doc_id}-c0000",
        doc_id=doc_id,
        repository=repository,
        role_in_generation=role_of(repository),
        text=text,
        ordinal=0,
        span=ChunkSpan(page_start=1, page_end=1),
        access=_access(),
        embedding_model_version="deterministic-hash-v1",
        metadata=metadata,
    )


async def _seed() -> None:
    container = get_container()
    chunks = {
        Repository.FINANCIAL: [
            _chunk(
                Repository.FINANCIAL,
                FINANCIAL_DOC_ID,
                "Acme Corp fiscal year 2024 revenue net income. Annual report for Acme "
                "Corp. Revenue and net income for fiscal year 2024 with total assets.",
                {"fiscal_year": 2024, "issuer": "Acme Corp", "subtype": "annual_report"},
            )
        ],
        # Exemplars = Halstead reference passages (knowledge_base/proposal_repository/
        # Halstead_Partners_Reference_Passages.pdf). They carry the advisory VOICE only —
        # no figures, using bracketed [metric] placeholders where a number would go — so
        # the small model mirrors a known-good style instead of inventing prose/numbers.
        Repository.PROPOSAL: [
            _chunk(
                Repository.PROPOSAL,
                "doc-ref-exec",
                "Halstead Partners has been engaged to assess the financial viability of the "
                "proposed program. Drawing on a bottom-up commercial model and a review of the "
                "competitive landscape, we conclude that the opportunity is attractive on a "
                "risk-adjusted basis and recommend that the company proceed. The program is "
                "expected to be earnings-accretive within the medium term and to strengthen the "
                "company's position in a growing, high-margin segment. We propose a stage-gated "
                "funding approach, with each subsequent capital release contingent on the "
                "completion of defined design, certification, and commercial milestones.",
                {"outcome": "won", "subtype": "reference_passage", "section_type": "executive_summary"},
            ),
            _chunk(
                Repository.PROPOSAL,
                "doc-ref-market",
                "The relevant market continues to expand, driven by sustained shifts in customer "
                "behaviour and by the migration of value toward differentiated, premium offerings. "
                "We see a credible path for the company to capture share at the upper end of this "
                "market, supported by its brand strength, distribution reach, and existing customer "
                "base. Beyond direct product economics, the proposal deepens engagement with the "
                "company's broader ecosystem and supports recurring, higher-margin revenue over time. "
                "While competitive intensity is rising, we believe a clearly positioned, "
                "differentiated offering mitigates the principal pricing risks.",
                {"outcome": "won", "subtype": "reference_passage", "section_type": "market_opportunity"},
            ),
            _chunk(
                Repository.PROPOSAL,
                "doc-ref-risk",
                "The base case is most sensitive to adoption pace, pricing, and input costs; we have "
                "stress-tested each of these and the program remains value-accretive across the range "
                "examined, indicating a robust risk-adjusted profile. The principal risks — "
                "slower-than-expected adoption, potential cannibalisation of existing lines, and "
                "component cost inflation — are, in our assessment, manageable through phased "
                "production, clear product tiering, and diversified sourcing. On this basis, we "
                "recommend that the company approve the program and release the initial tranche of "
                "funding, with subsequent capital contingent on milestone delivery.",
                {"outcome": "won", "subtype": "reference_passage", "section_type": "risk_recommendation"},
            ),
        ],
        # The company template: a text-only advisory proposal whose three sections
        # mirror the reference passages (executive summary → market opportunity →
        # risk assessment & recommendation). Structure/guidance only — no example
        # sentences — so nothing boilerplate leaks into the generated prose. The
        # assembler splits this one document into one locked section per heading.
        Repository.TEMPLATE: [
            _chunk(
                Repository.TEMPLATE,
                "doc-tmpl-advisory",
                "Advisory Proposal\n"
                "1. Executive Summary\n"
                "Set out the engagement, the assessment drawn from a review of the "
                "opportunity, and a clear recommendation on whether to proceed.\n"
                "2. Market Opportunity\n"
                "Set out the market context and the strategic rationale — why now, and "
                "the credible path to capturing the opportunity.\n"
                "3. Risk Assessment and Recommendation\n"
                "Set out the principal risks and their mitigations, then close with the "
                "recommendation and the proposed next steps.",
                {"status": "approved", "subtype": "advisory_proposal", "slot_count": 3},
            )
        ],
    }
    for repository, repo_chunks in chunks.items():
        embeddings = await container.embedder.embed_documents([c.text for c in repo_chunks])
        await container.vector_store.upsert(
            repository,
            [EmbeddedChunk(chunk=c, embedding=e) for c, e in zip(repo_chunks, embeddings)],
        )
    print(f"seeded vector store: financial({FINANCIAL_DOC_ID}) + proposal + template")


def main() -> None:
    os.environ.setdefault("ENVIRONMENT", "local")
    os.environ.setdefault("AIR_GAPPED", "true")
    asyncio.run(_seed())
    app = create_app()
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    print(f"serving seeded API on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
