# Phase 1 Handoff — Financial Ingestion Vertical Slice

> Read this first if you are starting a fresh session to build **Phase 1**. It is
> self-contained: what exists, how to run it, what to build next, and the
> acceptance bar. Architecture source of truth remains `docs/ARCHITECTURE_SUMMARY.md`
> (conflict precedence: ARCHITECTURE_SUMMARY → architecture → document-intelligence
> → rag-design → ui-design).

---

## 1. Where the project is

**Phase 0 (Foundations) is complete and verified.** The whole backend follows
Clean Architecture: `domain/` (pure entities + `ports/` Protocols) → `modules/`
(use-cases, mostly empty pending Phase 1+) → `infrastructure/` (adapters) →
`api/` (FastAPI). Dependencies point inward only.

### Built and tested (15 tests passing)
| Area | Location | Notes |
|---|---|---|
| Config | `app/core/config/settings.py` | Air-gapped, **fail-closed**; prod must use SLM |
| Policies | `app/core/policies/` | classifier θ, EQS weights + gate predicates, retrieval/context budgets, grounding floors |
| Domain | `app/domain/` | repositories, documents, chunks, proposals, generation, metrics, **ports** |
| Persistence | `app/infrastructure/persistence/postgres/` | SQLAlchemy 2.0 async, models + mappers + adapters + Alembic `0001_initial` |
| Vector store | `app/infrastructure/vector_store/chromadb/` | `ChromaVectorStore` (ACL pre+post filter), real + in-memory clients |
| Object store | `app/infrastructure/object_storage/` | `S3ObjectStore` + `InMemoryObjectStore` |
| Embedder | `app/infrastructure/embedding/` | `HttpEmbedder` + `DeterministicEmbedder` |
| LLM gateway | `app/infrastructure/llm_gateway/` | `ClaudeGateway` + `SlmGateway` + `EchoGateway` + factory |
| Composition root | `app/container.py` | binds every port to an adapter by `ENVIRONMENT` |
| App | `app/main.py`, `app/api/routers/health.py` | boots; `GET /health` shows wiring |
| Shared types | `packages/shared-types/` | TS mirror of domain enums/shapes |

**Every `domain/port` now has a working adapter** — so Phase 1 can run end-to-end.

### Key design rules already enforced (do not re-litigate)
- **3 repositories, distinct roles**, never merged: financial=evidence (only
  citable), proposal=exemplar, template=scaffold. Collection names:
  `repo_financial` / `repo_proposals` / `repo_templates`.
- **ACL is a retrieval pre-filter**: every chunk carries `AccessControl`
  (groups + engagement deal-team wall + classification). The vector store
  enforces it (engagement `where` pre-filter + fail-closed `permits` post-filter).
- **Air-gap**: all adapters use lazy imports / internal endpoints; no egress.
- **`content_hash` uniqueness** backs re-ingestion idempotency.

---

## 2. How to run things

A project virtualenv lives at **`backend/.venv`** (the global interpreter was
blocked by a locked `dotenv.exe`). Use it for everything:

```bash
# from backend/
./.venv/Scripts/python.exe -m pytest -q            # full suite (15 passing)
./.venv/Scripts/python.exe -m compileall -q app    # byte-compile

# run the app locally (in-memory object store / embedder / vector store / echo LLM)
#   needs PostgreSQL for the Unit of Work + migrations:
docker compose up -d postgres
# set env (copy backend/.env.example -> backend/.env), then:
./.venv/Scripts/python.exe -m alembic upgrade head
./.venv/Scripts/python.exe -m uvicorn app.main:app --reload   # GET /health
```

> Windows note: VS Code/`ty` may flag `Cannot find module sqlalchemy/pydantic` —
> that's the IDE pointing at the global interpreter, **not a real error**. Point
> the interpreter at `backend/.venv` (`.vscode/settings.json` already sets this).

Tests inject fakes directly (in-memory object store, `DeterministicEmbedder`,
`InMemoryChromaClient`, SQLite `session_factory`) so most Phase 1 unit/integration
tests need **no servers**. Follow the existing patterns in
`backend/tests/integration/`.

---

## 3. What Phase 1 is

**Build the financial-only ingestion vertical slice**: take an uploaded document
all the way into `repo_financial`, persisted and retrievable.

> **Extract / OCR → Normalize + PII/MNPI redact → Classify (financial path) →
> Repo-aware quality gate (financial) → Repo-specific metadata → Table-atomic
> chunking → Embed → ChromaDB (`repo_financial`, ACL-tagged) + catalog rows**

Scope to the **financial repository only** (proposal/template repos + the
curation gate are Phase 2). Prove one repository end-to-end before generalizing.

### Modules to implement (skeleton dirs already exist under `app/modules/ingestion/`)
| Stage | Module | Build |
|---|---|---|
| Extraction | `ingestion/extraction/` | PyMuPDF/Docling/python-docx/pptx → normalized doc model (text, tables, figures, pages) |
| OCR | `ingestion/ocr/` | PaddleOCR for image/scanned pages + per-region OCR confidence |
| Normalize+redact | `ingestion/normalization/` | clean text; PII/MNPI redaction + **redaction ledger** (separate from loss) |
| Classify | `ingestion/classification/` | local classifier → `SoftDistribution` (π_d) + confidence; use `DEFAULT_CLASSIFIER_POLICY`. Phase 1 can hard-route financial but still emit π_d |
| Quality gate | `ingestion/quality/` | compute `LossVector`/`QualityScores`/`EQS`; apply **financial** predicate (`CFR≥0.98, RPR≥0.99, EQS≥0.90`) from `DEFAULT_QUALITY_GATE_POLICY` → approve / re-extract / **human_review** |
| Metadata | `ingestion/metadata/` | financial layered metadata (issuer, fiscal_period, identifiers, `critical_figures_index`, table inventory) |
| Chunking | `ingestion/chunking/` | financial = structure-preserving, **tables atomic**, figure+caption together, period-tagged; emit `Chunk` entities |
| Embed+index | `ingestion/embedding/` | `EmbedderPort.embed_documents` → `VectorStorePort.upsert(repository, EmbeddedChunk[])` |
| Pipeline | `ingestion/pipeline/` | orchestrate stages; persist `Document` + chunk catalog rows in one `UnitOfWork`; emit lineage |
| Human review | `ingestion/human_review/` | queue for gate failures / low classifier confidence |

### Ports you will consume (all ready)
`ObjectStorePort` (store raw), `EmbedderPort`, `VectorStorePort` (upsert),
`DocumentCatalogPort` + `UnitOfWorkPort` (persist `Document`). Get them from
`app.container.get_container()`. Build use-cases against the **ports**, not the
adapters.

### Gaps to fill (intentionally deferred from Phase 0)
- **`document_chunks` has no port/adapter yet.** Add a `ChunkCatalogPort` in
  `domain/ports/` + a SQLAlchemy adapter (model `DocumentChunkRow` already
  exists) and expose it on the `UnitOfWork` so the pipeline persists the
  `chunk_id ↔ vector_id` mapping.
- **Quality columns** were intentionally left off `documents`. When the gate
  produces `QualityScores`, either add columns (new Alembic migration) or a
  `document_quality` table, and extend the catalog mapper.
- **`core/security`** services (identity/authz/acl/redaction) are skeletons. For
  Phase 1, ACL tags can come from the upload request context (engagement_id +
  caller groups); a full identity service can wait.
- **Upload API route** (`api/routers/`) + an `ingestion` router to trigger the
  pipeline.

---

## 4. Acceptance criteria for Phase 1

1. A PDF/DOCX/PPTX/PNG/JPG upload runs the full pipeline and lands embedded
   chunks in `repo_financial` plus catalog rows (`documents` + chunk mapping).
2. The financial quality gate is enforced; failures route to human review, not
   into the index.
3. Every chunk carries correct `AccessControl`; a query with a mismatched
   engagement/group cannot retrieve it (reuse the ACL test patterns).
4. Re-uploading the same file (same `content_hash`) is idempotent.
5. `π_d`, classifier confidence, quality scores, and redaction-ledger refs are
   recorded to lineage.
6. New tests pass with no servers (fakes/SQLite), following
   `backend/tests/integration/` patterns. Keep the suite green.

---

## 5. Conventions & gotchas
- Use `backend/.venv/Scripts/python.exe`. Keep `ruff`/`mypy --strict` clean.
- Populate `__init__.py` re-exports per package (existing pattern); they start as
  empty markers — **Read before Write** (the tool requires it).
- Mirror any new domain enum into `packages/shared-types` so frontend stays in sync.
- Persisted enums are stored as their `StrEnum` `.value`; reconstruct on read.
- Don't pool repositories into one ranking; don't let non-financial content
  become a citation. (Matters in Phase 3, but design Phase 1 metadata with it in mind.)

Memory files `project-conventions` and `phase-progress` carry the same context
across sessions.
