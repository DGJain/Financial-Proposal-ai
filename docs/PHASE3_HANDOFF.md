# Phase 3 Handoff — RAG Retrieval & Proposal Generation

> Read this first if you are starting a fresh session to build **Phase 3**. It is
> self-contained: what exists, how to run it, what to build next, and the
> acceptance bar. Architecture source of truth: `docs/ARCHITECTURE_SUMMARY.md`
> (conflict precedence: ARCHITECTURE_SUMMARY → architecture → document-intelligence
> → rag-design → ui-design). Phase 3 design lives in **`docs/rag-design.md`** (§1–§6).

---

## 1. Where the project is

**Phases 0, 1 and 2 are complete and verified — 29 tests passing.** Clean
Architecture throughout: `domain/` (pure entities + `ports/` Protocols) →
`modules/` (use-cases) → `infrastructure/` (adapters) → `api/` (FastAPI).
Dependencies point inward only.

### Built and tested
| Area | Location | Notes |
|---|---|---|
| Config / policies | `app/core/config`, `app/core/policies/` | air-gap fail-closed; classifier θ, **retrieval/context/grounding policy**, EQS weights + gates |
| Domain | `app/domain/` | repositories, documents, chunks, proposals, **generation**, metrics, ingestion, **ports** |
| Persistence | `app/infrastructure/persistence/postgres/` | SQLAlchemy 2.0 async; `documents`, `document_chunks`, `document_quality`, `generation_events` (+ 4 lineage child tables); Alembic `0001`,`0002` |
| Vector store | `app/infrastructure/vector_store/chromadb/` | `ChromaVectorStore` with **2-layer ACL** (engagement `where` pre-filter + fail-closed `permits` post-filter), `repo_*` collections, in-memory client |
| Embedder / LLM | `app/infrastructure/embedding`, `.../llm_gateway` | `DeterministicEmbedder`, `EchoGateway` (local) + `ClaudeGateway`/`SlmGateway` |
| Ingestion (P1/P2) | `app/modules/ingestion/` | full 3-repo ingestion + curation/anonymization gate; `IngestionEngine`, strategy registry |
| Composition root | `app/container.py` | binds every port by `ENVIRONMENT`; `ingestion_engine`, `curate_exemplar()` |
| App | `app/main.py`, `app/api/routers/` | `/health`, `/ingest/financial`, `/curate/{repository}` |

**The corpus side is done.** Phase 3 is the **read/generate** side: query the three
collections and produce a grounded proposal.

### Key rules already enforced (do not re-litigate)
- **Three repositories, distinct roles, never merged into one ranking**:
  financial = **evidence** (only citable), proposal = **exemplar** (style only),
  template = **scaffold** (structure only). Collections `repo_financial` /
  `repo_proposals` / `repo_templates`.
- **ACL is a retrieval pre-filter** — `VectorStorePort.query(repository, embedding,
  k=, acl=AclFilter(...), where=...)` already enforces the engagement wall +
  fail-closed group/classification post-filter. **Reuse it; do not re-implement ACL.**
- **Air-gap**: lazy imports, no egress. Local = in-process providers, no servers/secrets.
- Every chunk carries `repository` + `role_in_generation`; only `EVIDENCE`
  (financial) chunks may become citations (`Chunk.is_citable`).

---

## 2. How to run things

Project virtualenv at **`backend/.venv`** (use it for everything):

```bash
# from backend/
./.venv/Scripts/python.exe -m pytest -q            # full suite (29 passing)
./.venv/Scripts/python.exe -m compileall -q app    # byte-compile
```

Tests inject fakes directly (in-memory ChromaDB, `DeterministicEmbedder`,
`EchoGateway`, SQLite `session_factory`) so Phase 3 unit/integration tests need
**no servers**. Follow `backend/tests/integration/` patterns
(`test_ingestion_pipeline.py`, `test_curation_pipeline.py`, `test_chroma_vector_store.py`).

> `ruff`/`mypy` and the heavy libs (PyMuPDF, langgraph, anthropic…) are **not
> installed** in the venv — keep the runtime-critical path lazy-imported and tests
> serverless, as Phases 1–2 do. Match the existing lint/style conventions by hand.

---

## 3. What Phase 3 is

**Federated, role-aware retrieval → assembly → grounded generation** (rag-design.md):

> **brief + engagement (ACL)** → per-repo query formulation → **fan-out**: Financial
> (evidence, high *k*, grounding-looped) ∥ Proposal (exemplar, medium *k*,
> anonymized) ∥ Template (scaffold, low *k*) → **combine** into a role-tagged pool →
> **rank within each repo** → **context-budget assembly** (scaffold first, evidence
> into required slots, exemplars as style) → **generate** → **guardrails + numeric
> verification** (facts must cite financial only) → **confidence band** → **factual-
> health check** (financial factual share ≈100% or **block & regenerate**) → persist
> `GenerationEvent` lineage.

### The non-negotiable invariants (this is the dissertation's core)
1. **Never pool the three repositories into one similarity ranking.** Rank within
   each repository, then allocate a **context budget** by weight (evidence largest,
   scaffold a fixed slot, exemplars bounded). `rag-design.md` §4 explicitly rejects
   global pooling — a similar past proposal must never outrank the evidence.
2. **Only financial chunks become citations.** Exemplars/scaffold inform *how to
   say it / required shape*, never *what the numbers are*.
3. **Financial grounding gate is a floor.** Strong template/exemplar cannot rescue
   weak grounding → re-enter the grounding loop on the financial branch, else refuse.
4. **Factual-health check is a guardrail, not a tile.** If any non-financial repo
   contributes a factual citation (or financial factual share < floor) → **block &
   regenerate**; that is the signature of cross-engagement figure leakage.

### Modules to implement (skeleton dirs already exist)
| Stage | Module | Build |
|---|---|---|
| Query formulation | `modules/rag/query/` | brief + engagement → 3 per-repo queries (financial: entity/fiscal-period/line-items; proposal: type/sector/approach; template: type/sections) |
| Retrievers (fan-out) | `modules/rag/retrievers/` | 3 branch retrievers over `VectorStorePort.query` with per-branch `k` + repo `where` filters (financial scoped to engagement/period; proposal `anonymization`/`outcome`; template `status=approved`/`section_slot`). **Run concurrently (`asyncio.gather`).** Emit a role-tagged candidate pool |
| Ranking | `modules/rag/ranking/` | rank **within** each repo (financial: relevance + hard period/entity match; proposal: similarity + `outcome=won`/recency boost; template: type/section match) then allocate the **`ContextBudget`** |
| Assembly | `modules/rag/assembly/` | slot-fill: scaffold first → evidence into required slots → exemplars as style; honor `LLMGatewayPort.context_window`/`count_tokens`; build `GenerationRequest` |
| Grounding loop | `modules/rag/grounding/` | financial-branch loop (relax filters, broaden *k*, reformulate) up to `GroundingPolicy.max_grounding_loops`; below `grounding_floor` → refuse |
| Confidence | `modules/rag/confidence/` | per-repo composite gated by financial grounding → `ConfidenceBand` (HIGH/MEDIUM/LOW) |
| Generation | `modules/proposal_generation/generation/` | call `LLMGatewayPort.generate`/`stream`; produce sections bound to template slots → `Proposal`/`ProposalVersion` |
| Guardrails + numeric verify | `modules/proposal_generation/guardrails/`, `.../verification/` | every claim cites a financial chunk; **numeric verification** — figures in output must trace to a cited financial chunk; figure/entity-retention gate → `GenerationGateVerdict` |
| Contribution | `modules/metrics/contribution/` | compute `ContributionBreakdown` (context_share + factual_share) from citation lineage |
| Orchestrator | `modules/proposal_generation/graph/` | **fan-out/fan-in** orchestration of the above; assemble the `GenerationEvent` and persist via the audit port |

### Ports / policies you will consume (all ready)
- `VectorStorePort.query(repository, embedding, *, k, acl=AclFilter, where=)` →
  `list[ScoredChunk]` — **reuse for all three branches; ACL is already enforced.**
- `EmbedderPort.embed_query(text)` for query vectors.
- `LLMGatewayPort` (`generate`/`stream`/`count_tokens`/`context_window`) — local
  `EchoGateway` is deterministic and **emits no figures** (safe for gates).
- `AuditLogPort.append(GenerationEvent)` via `UnitOfWorkPort.audit` — persistence,
  mapper and `generation_events` (+ child) tables already exist (round-trip tested).
- `DEFAULT_RETRIEVAL_POLICY` in `core/policies/retrieval.py`: `BranchBudget`
  (financial_k=40, proposal_k=8, template_k=1), `ContextBudget` (0.60/0.25/0.15,
  8192 tok), `GroundingPolicy` (floor 0.60, high band 0.80, max 2 loops,
  `min_financial_factual_share=0.999`, `max_regeneration_attempts=1`).

### Domain types you will produce (already defined — Phase 0)
`app/domain/generation/`: `GenerationEvent` (the lineage record), `RetrievalHit`,
`Citation` (repository should always be FINANCIAL), `StageTiming`
(`GenerationStage`: rewrite/retrieve/ground/generate/total), `GateOutcome`
(`GenerationGateVerdict`: PASS/BLOCK_REGENERATE/REFUSE). `app/domain/metrics/`:
`ContributionBreakdown`, `RepositoryShare` (+ `factual_health_ok(...)`).
`app/domain/proposals/`: `Proposal`, `ProposalVersion`, `ProposalSection`
(structure locked, only `body` editable), `ConfidenceBand`, `GenerationOutcome`.

### Gaps to fill (intentionally deferred)
- **`Proposal` has no port/adapter yet** — add a `ProposalRepositoryPort` in
  `domain/ports/` + a SQLAlchemy adapter and table (Alembic `0003`) + mapper, and
  expose it on the `UnitOfWork`, so drafts/versions persist. (`GenerationEvent`
  persistence already exists; the `Proposal` aggregate does not.)
- **Generation API route** — `api/routers/generate.py` (`POST /generate`) returning
  the proposal + confidence band + contribution + report id. Add `container`
  factory `generate_proposal()`.
- **A retrieval/generation use-case** assembled in the container against the ports.
- **Section-level split routing** (θ_split) is still deferred from Phase 2 —
  out of scope for Phase 3.

### LangGraph note
`langgraph` is a declared dependency but **not installed** in the venv. Build the
fan-out/fan-in as plain `asyncio.gather` orchestration inside the use-case (pure,
testable, serverless). If you want a LangGraph graph, make it a **thin optional
infrastructure wrapper with a lazy import** — never put graph-framework types in
the use-case or domain.

---

## 4. Acceptance criteria for Phase 3

1. A proposal brief + engagement context runs the full pipeline and returns a
   grounded `Proposal` with a `ConfidenceBand`, citations, and a persisted
   `GenerationEvent` (replayable Execution Report).
2. Retrieval fans out to all three collections **concurrently**, ACL-pre-filtered;
   a caller in the wrong engagement/group retrieves nothing (reuse ACL test patterns).
3. **Within-repo ranking + context budget** is applied — never a single global
   ranking. Wrong-period financial evidence is dropped, not down-weighted.
4. **Every citation resolves to `repo_financial`.** A planted exemplar/template
   "fact" never becomes a citation.
5. **Financial grounding gate**: below floor → grounding loop, then **refuse** (a
   refused run still persists a `GenerationEvent` with reason + zero citations).
6. **Factual-health guardrail**: a generation whose factual share isn't ~100%
   financial is **blocked & regenerated** (or refused) — verified by a test that
   forces a non-financial factual citation.
7. `ContributionBreakdown` (context + factual share) is computed and recorded.
8. New tests pass with **no servers** (fakes/SQLite/Echo), following
   `backend/tests/integration/` patterns. Keep the suite green (29 → more).

---

## 5. Conventions & gotchas
- Use `backend/.venv/Scripts/python.exe`. Keep `ruff`/`mypy --strict` clean by hand
  (not installed locally). Build against **ports**, not adapters; get them from
  `app.container.get_container()`.
- Populate `__init__.py` re-exports per package (existing pattern) — **Read before
  Write** (the tool requires it; many are empty markers).
- Mirror any new domain enum into `packages/shared-types/src/enums/` (the `as const`
  + union pattern); no JS toolchain locally, so match the pattern by hand.
- Persisted enums stored as their `StrEnum` `.value`; reconstruct on read. UoW
  attributes are typed as the **port** Protocols (invariance) — follow that when
  adding `ProposalRepositoryPort`.
- The assembler must size context against `LLMGatewayPort.context_window` (the
  *smaller* SLM window), not a prototype window.
- **Recommended build order** (one coherent slice, like Phases 1–2): query →
  retrievers (fan-out) → within-repo ranking + budget → assembly → generation
  (Echo) → guardrails + numeric verification → confidence → contribution → grounding
  loop / refuse → persist `GenerationEvent`; then `Proposal` persistence + `/generate`
  route. Consider asking the user the same scoping questions Phase 2 used (full pass
  vs. slice; what to defer).

Memory files `project-conventions` and `phase-progress` carry the same context
across sessions; `phase-progress` records that Phases 0–2 are done and Phase 3 is next.
