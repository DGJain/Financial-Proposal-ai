"""Tests for the local AI-plane adapters (object store, embedder, LLM gateway).

These verify the in-process implementations the composition root selects for
``ENVIRONMENT=local`` — the ones Phase 1 ingestion runs against without servers.
The real S3/HTTP/Claude/SLM adapters are thin lazy-import wrappers exercised
against live services, not here.
"""

from __future__ import annotations

import pytest

from app.domain.ports.llm_gateway import GenerationRequest
from app.infrastructure.embedding.deterministic import DeterministicEmbedder
from app.infrastructure.llm_gateway.echo import EchoGateway
from app.infrastructure.object_storage.in_memory import InMemoryObjectStore


# --- object store ------------------------------------------------------------


async def test_object_store_put_get_exists() -> None:
    store = InMemoryObjectStore()
    uri = await store.put_raw("eng-7/report.pdf", b"%PDF-bytes", content_type="application/pdf")
    assert uri == "s3://raw-originals/eng-7/report.pdf"
    assert await store.exists(uri) is True
    assert await store.get(uri) == b"%PDF-bytes"

    versioned = await store.put_versioned("tmpl/exec.docx", b"docx", content_type="application/octet-stream")
    assert versioned.startswith("s3://versioned-originals/")
    assert await store.exists("s3://raw-originals/missing") is False
    with pytest.raises(FileNotFoundError):
        await store.get("s3://raw-originals/missing")


# --- deterministic embedder --------------------------------------------------


async def test_embedder_is_deterministic_and_fixed_dim() -> None:
    embedder = DeterministicEmbedder(dim=128)
    a1 = await embedder.embed_query("quarterly revenue grew")
    a2 = await embedder.embed_query("quarterly revenue grew")
    assert a1 == a2
    assert len(a1) == 128
    assert embedder.model_version == "deterministic-hash-v1"


async def test_embedder_similar_text_closer_than_unrelated() -> None:
    embedder = DeterministicEmbedder(dim=256)
    docs = await embedder.embed_documents(
        ["annual revenue and net income grew", "annual revenue and net profit grew", "the cat sat"]
    )

    def cos(x: list[float], y: list[float]) -> float:
        return sum(a * b for a, b in zip(x, y, strict=True))

    near = cos(docs[0], docs[1])  # share most tokens
    far = cos(docs[0], docs[2])  # disjoint
    assert near > far


# --- echo gateway ------------------------------------------------------------


async def test_echo_gateway_generate_and_stream() -> None:
    gateway = EchoGateway()
    assert gateway.model_id == "echo-local"
    assert gateway.context_window == 8192

    request = GenerationRequest(system="You are grounded.", prompt="Draft a proposal.", max_output_tokens=256)
    result = await gateway.generate(request)
    assert "echo-draft" in result.text
    assert result.model_id == "echo-local"
    assert result.input_tokens > 0 and result.output_tokens > 0

    streamed = "".join([token async for token in gateway.stream(request)])
    assert streamed.strip() == result.text.strip()
    assert await gateway.count_tokens("one two three") == 3
