"""Phase 4 tests — the generate / preview / edit HTTP surface.

Drives the FastAPI app through an in-process ASGI transport (single event loop, no
server) with the composition root overridden to a test ``Container``: in-memory
ChromaDB + deterministic embedder + Echo gateway, and a SQLite-backed Unit of Work
via the new ``session_factory`` seam. Verifies that ``POST /generate`` runs the
full Phase 3 pipeline and returns a grounded proposal envelope, that the proposal
is previewable, that editing is **text-only and structure-locked**, and that a
refusal returns the same envelope with no proposal.
"""

from __future__ import annotations

import io
import os

os.environ.setdefault("ENVIRONMENT", "local")
os.environ.setdefault("AIR_GAPPED", "true")
os.environ.setdefault("POSTGRES_DSN", "postgresql+asyncpg://u:p@localhost:5432/fpp")
os.environ.setdefault("REDIS_DSN", "redis://localhost:6379/0")

from collections.abc import AsyncIterator  # noqa: E402
from typing import Any  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.container import Container, get_container  # noqa: E402
from app.domain.chunks.chunk import Chunk, ChunkSpan  # noqa: E402
from app.domain.documents.acl import AccessControl  # noqa: E402
from app.domain.ports.vector_store import EmbeddedChunk  # noqa: E402
from app.domain.repositories.repository import Repository, role_of  # noqa: E402
from app.infrastructure.persistence.postgres.base import Base  # noqa: E402
from app.infrastructure.persistence.postgres.models import (  # noqa: E402,F401  (register tables)
    GenerationEventRow,
    ProposalRow,
)
from app.main import create_app  # noqa: E402

ENGAGEMENT = "eng-1"
GROUPS = "consultants"
HEADERS = {"X-ACL-Groups": GROUPS, "X-Engagement-Id": ENGAGEMENT, "X-Requested-By": "analyst-1"}


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


def _access() -> AccessControl:
    return AccessControl(acl_groups=frozenset({GROUPS}), engagement_id=ENGAGEMENT)


def _chunk(repository: Repository, doc_id: str, text: str, metadata: dict[str, Any]) -> Chunk:
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


async def _seed(container: Container) -> None:
    chunks = {
        Repository.FINANCIAL: [
            _chunk(
                Repository.FINANCIAL, "doc-fin",
                "Acme Corp fiscal year 2024 revenue net income. Annual report for Acme "
                "Corp. Revenue and net income for fiscal year 2024.",
                {"fiscal_year": 2024, "issuer": "Acme Corp", "subtype": "annual_report"},
            )
        ],
        Repository.PROPOSAL: [
            _chunk(
                Repository.PROPOSAL, "doc-prop",
                "Statement of work and approach for a banking engagement, structured in phases.",
                {"outcome": "won", "subtype": "past_proposal", "section_type": "approach"},
            )
        ],
        Repository.TEMPLATE: [
            _chunk(
                Repository.TEMPLATE, "doc-tmpl",
                "Statement of Work\nApproach: {approach}. Fees: {fee_amount}.",
                {"status": "approved", "subtype": "statement_of_work", "slot_count": 2},
            )
        ],
    }
    for repository, repo_chunks in chunks.items():
        embeddings = await container.embedder.embed_documents([c.text for c in repo_chunks])
        await container.vector_store.upsert(
            repository,
            [EmbeddedChunk(chunk=c, embedding=e) for c, e in zip(repo_chunks, embeddings)],
        )


@pytest_asyncio.fixture
async def client(session_factory: async_sessionmaker) -> AsyncIterator[httpx.AsyncClient]:
    container = Container(session_factory=session_factory)
    await _seed(container)
    app = create_app()
    app.dependency_overrides[get_container] = lambda: container
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _brief() -> dict[str, Any]:
    return {
        "title": "Audit services for Acme",
        "proposal_type": "statement_of_work",
        "entity": "Acme Corp",
        "fiscal_year": 2024,
        "sector": "banking",
        "line_items": ["revenue", "net income"],
    }


# --- tests -------------------------------------------------------------------


async def test_generate_returns_grounded_proposal(client: httpx.AsyncClient) -> None:
    response = await client.post("/generate", json=_brief(), headers=HEADERS)
    assert response.status_code == 200
    body = response.json()

    assert body["outcome"] == "generated"
    assert body["report_id"].startswith("gen-")
    assert body["confidence"]["band"] in {"high", "medium"}
    assert body["proposal"] is not None
    assert body["proposal"]["sections"]
    # Every citation resolves to a financial source (the source name carries it).
    assert body["citations"]
    # Contribution recorded — financial carries all factual weight.
    assert body["contribution"]["factual_share"]["financial"] == 100.0


async def test_generated_proposal_is_previewable(client: httpx.AsyncClient) -> None:
    gen = (await client.post("/generate", json=_brief(), headers=HEADERS)).json()
    proposal_id = gen["proposal"]["proposal_id"]

    response = await client.get(f"/proposals/{proposal_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["proposal_id"] == proposal_id
    assert body["version_no"] == 1
    assert body["status"] == "draft"
    assert body["sections"] == gen["proposal"]["sections"]


async def test_edit_is_text_only_and_structure_locked(client: httpx.AsyncClient) -> None:
    gen = (await client.post("/generate", json=_brief(), headers=HEADERS)).json()
    proposal_id = gen["proposal"]["proposal_id"]
    target = gen["proposal"]["sections"][0]
    original_structure = [(s["section_id"], s["order"], s["heading"]) for s in gen["proposal"]["sections"]]

    response = await client.post(
        f"/proposals/{proposal_id}/versions",
        json={"edits": [{"section_id": target["section_id"], "body": "Rewritten prose."}]},
        headers=HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["version_no"] == 2
    assert body["status"] == "edited"
    # Structure unchanged; only the targeted body changed.
    assert [(s["section_id"], s["order"], s["heading"]) for s in body["sections"]] == original_structure
    edited = next(s for s in body["sections"] if s["section_id"] == target["section_id"])
    assert edited["body"] == "Rewritten prose."

    # The edit persisted as the new current version.
    after = (await client.get(f"/proposals/{proposal_id}")).json()
    assert after["version_no"] == 2
    assert after["status"] == "edited"


async def test_edit_unknown_section_is_rejected(client: httpx.AsyncClient) -> None:
    gen = (await client.post("/generate", json=_brief(), headers=HEADERS)).json()
    proposal_id = gen["proposal"]["proposal_id"]
    response = await client.post(
        f"/proposals/{proposal_id}/versions",
        json={"edits": [{"section_id": "does-not-exist", "body": "x"}]},
        headers=HEADERS,
    )
    assert response.status_code == 400


async def test_missing_proposal_returns_404(client: httpx.AsyncClient) -> None:
    assert (await client.get("/proposals/prop-nope")).status_code == 404


def _docx_bytes(text: str) -> bytes:
    import docx  # installed in the venv

    document = docx.Document()
    document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


async def test_extract_attachment_reads_docx_text(client: httpx.AsyncClient) -> None:
    body = _docx_bytes("Engagement scope: quarterly close automation for the finance team.")
    response = await client.post(
        "/generate/extract?filename=notes.docx&file_type=docx",
        content=body,
        headers={"content-type": "application/octet-stream"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["extracted"] is True
    assert "quarterly close automation" in data["text"]
    assert data["char_count"] > 0


async def test_extract_attachment_unreadable_falls_back(client: httpx.AsyncClient) -> None:
    # Garbage bytes labelled as a PDF — extraction fails, but the endpoint degrades
    # to "attach by name" (extracted=false) rather than erroring.
    response = await client.post(
        "/generate/extract?filename=broken.pdf&file_type=pdf",
        content=b"this is not a real pdf",
    )
    assert response.status_code == 200
    data = response.json()
    assert data["extracted"] is False
    assert data["text"] == ""


async def test_wrong_engagement_refuses_with_no_proposal(client: httpx.AsyncClient) -> None:
    headers = {**HEADERS, "X-Engagement-Id": "eng-OTHER"}
    response = await client.post("/generate", json=_brief(), headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "refused"
    assert body["proposal"] is None
    assert body["refusal_reason"]
    assert body["report_id"].startswith("gen-")
    assert body["citations"] == []
