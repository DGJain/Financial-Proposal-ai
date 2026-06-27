# Architecture Summary — Financial Proposal Platform

**Status:** Single source of truth · consolidates `architecture.md`, `document-intelligence.md`, `rag-design.md`, `ui-design.md`.

---

## Project Goal

An air-gapped, internal-only platform that generates **finance-grade proposals** grounded strictly in an organisation's private knowledge. A user uploads financial documents and requests a proposal; the system retrieves from three governed knowledge repositories, assembles a role-aware grounded prompt, generates a draft with an enterprise model, and presents it for light editing and export. Every figure in the output is traceable to source. The system **refuses rather than answers outside its corpus.**

## Security Constraints

- **Air-gapped & internal-only** — no external API calls; local embedding model, local classifier, local SLM (prod) / Claude (proto).
- **ACL/ABAC everywhere** — RBAC + document-level ACLs and deal-team walls applied as retrieval pre-filters; carried from ingestion metadata into every query.
- **PII/MNPI redaction** at ingestion, with a redaction ledger separate from loss measurement.
- **Hard fact-grounding rule:** every cited fact must resolve to the **Financial Documents** repository, scoped to the current engagement. Proposal exemplars are anonymized/redacted and used only for *how to say it*, never *what the numbers are* — preventing cross-engagement MNPI/figure leakage. Enforced at context assembly **and** numeric verification.
- **Immutable audit lineage** — classification, `π_d`, retrieval hits, scores, and downloads are logged and replayable.

## Technology Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js (server components for the audit-linked report) |
| API / Orchestration | FastAPI · LangGraph (fan-out/fan-in proposal graph) |
| AI plane | Local embedding model · Enterprise model (SLM prod / Claude proto) via LLM Gateway · Guardrails · local repository classifier (small NER/SLM + rules) |
| Vector store | ChromaDB — **3 ACL-tagged collections** |
| Metadata / SoR | PostgreSQL — catalog · lineage · audit · metrics |
| Cache / Queue | Redis — retrieval cache (per-repo) · sessions · streams · queue |
| Files | Object storage — raw + versioned originals |

## Knowledge Repositories

Three repositories, one ingestion pipeline, separate collections — each with a **distinct role** (never merged into one global ranking).

| Repository | Collection | Role | Contributes | May **not** contribute |
|---|---|---|---|---|
| **Financial Documents** | `repo_financial` | Evidence (facts) | Cited facts/figures for the engagement | — |
| **Proposal Knowledge** | `repo_proposals` | Exemplar (style) | Structure, framing, language (few-shot) | Factual figures |
| **Template** | `repo_templates` | Scaffold (shape) | Section skeleton, slots, boilerplate | Facts / client content |

User uploads flow **only** into `repo_financial`. `repo_proposals` and `repo_templates` accept content **only via a curation/approval gate**. Approved generated proposals are re-ingested into `repo_proposals` (curation feedback loop). Each collection is independently namespaced, versioned, and snapshotted.

## Ingestion Architecture

Single pipeline, three targets:

> **Extract / OCR → Normalize + PII/MNPI redact → Classify repository → Repo-aware quality gate → Repo-specific metadata → Repo-specific chunking → Embed → ChromaDB (namespaced + ACL)**

- **Repository classifier** (local) emits a soft distribution `π_d = (π_FIN, π_PROP, π_TMPL)`, Σ=1, plus confidence. Route = `argmax(π_d)` above `θ_cls`; multi-repo documents above `θ_split` are split-routed at section level; low confidence → human review.
- **Layered metadata:** common base (identity, provenance, `acl_tags`, `sensitivity`, `quality`, `repository`/`repo_confidence`/`π_d`, `lineage_root`) + a repository-specific schema (e.g. `critical_figures_index` for financial, `outcome`/`sections_present` for proposals, `placeholder_slots`/`section_taxonomy` for templates). Repo-specific fields become filterable ChromaDB metadata.
- **Repo-specific chunking:** Financial = structure-preserving, **tables atomic**, figure+caption kept together, period-tagged; Proposal = section-semantic, larger narrative windows; Template = structure/placeholder-aware reusable units with slots preserved verbatim.
- **Three repo-aware quality gates** (`EQS = Σ wₘ·Sₘ`, `Sₘ = 1−Lₘ`):
  - Financial: `CFR ≥ 0.98` and `RPR ≥ 0.99` and `EQS_fin ≥ 0.90`, no critical low-confidence region (strictest).
  - Proposal: `EQS_prop ≥ 0.85` and Section Coverage `SC ≥ 0.90` and `conf ≥ θ_cls`.
  - Template: Placeholder Integrity `PI ≥ 0.99` and Structural Fidelity `SF ≥ 0.95` and `EQS_tmpl ≥ 0.90`.
  - Failures → re-extraction or human review.

## Private RAG Architecture

Federated, role-aware retrieval (LangGraph fan-out → combine → rerank → assemble → generate):

- **Three parallel branches** with their own query, filters, candidate budget, and scoring profile:
  - *Financial* — hybrid dense+sparse, ACL pre-filtered, scoped to engagement/entity/period, high *k*; **the only branch whose chunks become citations**; subject to the grounding loop + numeric verification.
  - *Proposal* — semantic similarity of brief to past proposals, anonymized-only, medium *k*; boosted by `outcome=won` and recency.
  - *Template* — near-deterministic match by proposal type/sections, low *k* (often top-1).
- **Two-stage ranking, never globally pooled by raw score:** rank within each repository, then allocate a **context budget by configurable weights** so each role gets a guaranteed share (evidence highest, fixed scaffold slot, bounded exemplar share). Recorded with the generation event.
- **Per-repository confidence with a financial grounding gate** (floor): if evidence grounding is below threshold, refuse or re-enter the grounding loop — regardless of strong template/exemplar signals.

## Proposal Generation Workflow

`Upload → Document processing → Retrieve Financial → Retrieve Proposal → Retrieve Template → Context assembly (scaffold first · evidence into required_fields · exemplars as style) → Enterprise model (stream) → Guardrails + numeric verification → Figure/entity-retention gate → Save v1 → Preview → Side-by-side edit (new version) → Approve & Download (audited) → Re-ingest approved proposal into repo_proposals`. The three retrievals run concurrently; the assembler preserves precedence facts → exemplar → scaffold.

## Metrics Dashboard

Three stacked zones: (1) **Repository cards** (×5: Financial Docs, Proposal Examples, Templates, Embedded Chunks, Last Ingestion — live from PostgreSQL/ChromaDB via cached `/metrics/repository`); (2) **Generation health** (grounding/extraction/refusal/proposal stat cards + 7-day chart + information-loss donut); (3) **Prompt History Analytics** table. Two contribution metric families per generation:

- **Corpus / Context Contribution %** — knowledge-base composition and share of assembled context per repository (`Σ wₐ·π_dᴿ / Σ wₐ`).
- **Generation / Factual Contribution %** — lineage-based share of grounded claims cited to each repository. **Health-check guardrail:** Financial factual share should be ≈100%; if any non-financial repo contributes facts, generation is **blocked and regenerated** (signature of figure leakage).

## Prompt History

Record list with search + status filters; each row carries the full 9-field analytics set (Prompt, Timestamp, Files Used, Proposal Generated ✓/◐/✕, Processing Time, OCR Confidence, Extraction Quality, Information Loss %, Repository Contribution %). Every row drills into a read-only, audit-linked **Execution Report** (`/report/[id]`) — 10 sections: prompt verbatim, uploaded files, retrieved financial docs/proposal examples/templates (with scores), OCR & extraction quality, information-loss analysis + gate verdict, generation stage timeline, and source citations (source · page). Refused runs still open a report (zero docs, refusal reason, no generation stages).

## Proposal Preview

50/50 split — generated proposal left, **text-only editable** right ("structure & template locked"). Headings, IDs, section order, and the template are non-editable; only prose within existing blocks may change, keeping every sentence traceable and the template intact for export. Export renders the locked template with embedded lineage metadata; the information-loss gate governs whether export is enabled.

## Deployment Overview

Kubernetes, two namespaces:
- **`ai` (GPU):** Embedding server + SLM serving.
- **`data` (StatefulSets):** ChromaDB serving the three collections (each on a PV with independent snapshots), PostgreSQL primary + replica, Redis HA, object storage.

No new services or egress paths beyond the base; ChromaDB hosts three independently snapshotted/restorable collections. Templates and curated proposals follow a slower, versioned change cadence than the higher-churn financial corpus.
