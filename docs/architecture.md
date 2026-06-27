# Architecture Update — Multi-Repository Knowledge & Proposal Flow

**Revision:** R2 · **Scope:** Delta to the base architecture. Only changed sections are reproduced below.
**Summary of change:** Three governed knowledge repositories are introduced, all ingested into ChromaDB as separate collections through the existing ingestion pipeline. Proposal generation now retrieves from **all three** repositories before the enterprise model is invoked.

---

## 0. New Concept — Three Knowledge Repositories

All three are ingested via the **same ingestion pipeline** (extract → quality-score → normalize/redact → chunk → embed → ACL-tag) and stored as **separate ChromaDB collections**, with metadata cataloged in PostgreSQL and raw files in object storage. They contribute different things to a proposal:

| Repository | ChromaDB collection | Contents | Role in proposal |
|---|---|---|---|
| **Financial Documents** | `repo_financial` | Annual Reports, Financial Statements, Investment Reports, Uploaded User Documents | **The facts** — substantive grounding content. |
| **Proposal Knowledge** | `repo_proposals` | 20–30 curated examples (banking consulting, investment, risk assessment) + previously generated **approved** proposals | **The exemplars** — style, framing, domain language (few-shot). |
| **Template** | `repo_templates` | Executive Summary, Proposal Structure, Pricing, Timeline, Risk Assessment templates | **The scaffold** — required structure and sections. |

Separation of concerns: *facts* (financial) + *how good proposals read* (proposal KB) + *required shape* (templates). Approved generated proposals are re-ingested into `repo_proposals`, forming a curation feedback loop.

---

## 1. High-Level Architecture *(updated — Data Plane + proposal retrieval fan-out)*

```mermaid
flowchart TB
    subgraph APP["Application & Orchestration Plane"]
        API["FastAPI Services"]
        LG["LangGraph Orchestrator"]
        ING["Ingestion & Extraction Service"]
        ASM["Multi-Repository Context Assembler"]
    end

    subgraph AI["AI Plane"]
        GWY["LLM Gateway / Model Abstraction"]
        EMB["Embedding Model (local)"]
        GEN["Enterprise Model<br/>SLM (prod) / Claude (proto)"]
        GUARD["Guardrails"]
    end

    subgraph DATA["Data Plane"]
        subgraph CHROMA["ChromaDB (3 collections)"]
            RF["repo_financial"]
            RP["repo_proposals"]
            RT["repo_templates"]
        end
        PG["PostgreSQL — metadata · history · audit · metrics"]
        REDIS["Redis — cache · session · stream · queue"]
        OBJ["Object Storage — raw & versioned files"]
    end

    API --> LG
    LG --> ING --> OBJ
    ING --> EMB
    EMB --> RF
    EMB --> RP
    EMB --> RT
    LG --> ASM
    ASM --> RF
    ASM --> RP
    ASM --> RT
    ASM --> GWY --> GEN
    GWY --> GUARD
    LG --> PG
    API --> REDIS
```

The new element is the **Multi-Repository Context Assembler**: for proposal generation it queries all three collections (ACL-filtered) and merges results into a single grounded prompt before the model is called.

---

## 2. Data Plane *(updated)*

ChromaDB now hosts **three logical collections** rather than one. Each is independently namespaced, ACL-tagged, versioned, and backed up. PostgreSQL gains a `repository` dimension on the document catalog so every chunk is attributable to its source repository.

```mermaid
flowchart LR
    subgraph CH["ChromaDB"]
        RF["repo_financial<br/>annual reports · statements · investment reports · user uploads"]
        RP["repo_proposals<br/>curated examples · approved proposals"]
        RT["repo_templates<br/>exec summary · structure · pricing · timeline · risk"]
    end
    PG["PostgreSQL<br/>catalog (+repository, +subtype) · lineage · evaluations · audit"]
    OBJ["Object Storage<br/>raw + versioned source files"]
    RD["Redis<br/>retrieval cache (per-repo) · sessions · queue"]

    PG <-->|chunk_id <-> vector_id| CH
    PG -->|object_uri| OBJ
    RD -.-> CH
```

---

## 3. Private RAG Architecture *(updated)*

**Ingestion** is unchanged in shape but now routes each document to one of three target collections based on its repository classification. **Retrieval** gains a proposal-specific fan-out: chat/Q&A still queries `repo_financial`, but proposal generation queries all three collections and assembles a blended context.

```mermaid
flowchart TB
    subgraph INGEST["Ingestion (single pipeline, 3 targets)"]
        D["Source / Uploaded Document"]
        CLS["Repository Classifier<br/>financial · proposal · template"]
        P["Extract · OCR · Quality-score · Normalize · Redact · Chunk · Embed"]
        D --> CLS --> P
        P -->|financial| RF["repo_financial"]
        P -->|proposal| RP["repo_proposals"]
        P -->|template| RT["repo_templates"]
    end

    subgraph PROP["Proposal Retrieval (fan-out across all 3)"]
        REQ["Proposal request (+ACL)"]
        Q1["Retrieve facts -> repo_financial"]
        Q2["Retrieve exemplars -> repo_proposals"]
        Q3["Retrieve structure -> repo_templates"]
        ASM["Context Assembler<br/>merge · dedupe · rank · figure-retention check"]
        GEN["Enterprise Model via LLM Gateway"]
        REQ --> Q1 --> ASM
        REQ --> Q2 --> ASM
        REQ --> Q3 --> ASM
        ASM --> GEN
    end

    RF --> Q1
    RP --> Q2
    RT --> Q3
```

Retrieval order is **Financial → Proposal → Template → Assembly** as specified; within the LangGraph node the three queries may execute concurrently while the assembler preserves that precedence when composing the prompt (facts first, then exemplar framing, then template scaffold).

---

## 4. Data Flow Diagrams *(updated — proposal generation)*

### 4.1 New end-to-end proposal flow

```mermaid
flowchart LR
    A["Document Upload"] --> B["Document Processing<br/>extract · OCR · quality · chunk · embed"]
    B --> C["Financial Repository Retrieval"]
    C --> D["Proposal Repository Retrieval"]
    D --> E["Template Repository Retrieval"]
    E --> F["Context Assembly"]
    F --> G["Enterprise Model"]
    G --> H["Proposal Generation"]
    H --> I["Proposal Preview"]
    I --> J["User Editing (side-by-side)"]
    J --> K["Download"]
    K -.->|"if approved"| L["Re-ingest into repo_proposals"]
    L -.-> D
```

### 4.2 Proposal generation sequence *(replaces base §5.3)*

```mermaid
sequenceDiagram
    actor User
    participant FE as Next.js
    participant API as FastAPI
    participant LG as LangGraph (Proposal)
    participant RF as repo_financial
    participant RP as repo_proposals
    participant RT as repo_templates
    participant ASM as Context Assembler
    participant GW as LLM Gateway
    participant M as Enterprise Model
    participant EV as Information-Loss Eval
    participant PG as PostgreSQL

    User->>FE: Upload doc + request proposal
    FE->>API: Submit (params + ACL)
    API->>LG: Start proposal graph
    Note over LG: Document processing (if new upload)
    LG->>RF: Retrieve facts (ACL-filtered)
    LG->>RP: Retrieve exemplar proposals
    LG->>RT: Retrieve templates
    RF-->>ASM: Financial context
    RP-->>ASM: Exemplar context
    RT-->>ASM: Template scaffold
    ASM->>GW: Assembled grounded prompt
    GW->>M: Generate
    M-->>GW: Draft (stream)
    GW-->>LG: Guardrail-checked draft
    LG->>EV: Figure/entity-retention check (gate)
    LG->>PG: Save proposal v1
    LG-->>FE: Stream to Preview pane
    User->>FE: Edit side-by-side
    FE->>API: Save edits (new version)
    User->>FE: Approve & Download
    API->>PG: Log download (audit)
    API->>LG: Re-ingest approved proposal -> repo_proposals
```

---

## 5. Deployment Architecture *(updated — Data namespace)*

The only deployment change is within the data namespace: the ChromaDB StatefulSet now serves three collections on persistent volumes, each independently snapshotted and restorable. No new services or egress paths are introduced.

```mermaid
flowchart TB
    subgraph NS_AI["Namespace: ai (GPU)"]
        EMBS["Embedding Server"]
        SLM["SLM Serving"]
    end
    subgraph NS_DATA["Namespace: data (StatefulSets)"]
        subgraph CHR["ChromaDB"]
            C1["repo_financial (PV + snapshots)"]
            C2["repo_proposals (PV + snapshots)"]
            C3["repo_templates (PV + snapshots)"]
        end
        PG[("PostgreSQL primary + replica")]
        RDS[("Redis HA")]
        OBJ[("Object Storage")]
    end
    EMBS --> C1
    EMBS --> C2
    EMBS --> C3
    SLM -.-> CHR
    PG <--> CHR
```

---

## 6. Repository Storage Architecture *(new)*

Each repository spans three stores with a shared governance model. ChromaDB holds the vectors per collection; PostgreSQL is the catalog/lineage system of record (now keyed by `repository` and `subtype`); object storage holds raw files. The Proposal Knowledge and Template repositories add a **curation/approval gate** before ingestion — they are manually curated, not open-upload.

```mermaid
flowchart TB
    subgraph SRC["Sources"]
        UP["User Uploads"]
        CUR["Curated Examples / Templates<br/>(manual, approval-gated)"]
        APR["Approved Generated Proposals"]
    end

    subgraph GATE["Governance"]
        CLS["Classifier -> repository + subtype"]
        APV["Curation / Approval Gate"]
    end

    PIPE["Ingestion Pipeline<br/>extract · quality · chunk · embed · ACL-tag"]

    subgraph STORE["Storage Layout"]
        subgraph CH["ChromaDB collections"]
            RF["repo_financial"]
            RP["repo_proposals"]
            RT["repo_templates"]
        end
        PG["PostgreSQL catalog<br/>repository · subtype · version · ACL · lineage"]
        OBJ["Object Storage<br/>raw + versioned originals"]
    end

    UP --> CLS
    APR --> APV
    CUR --> APV
    APV --> CLS
    CLS --> PIPE
    PIPE --> RF
    PIPE --> RP
    PIPE --> RT
    PIPE --> PG
    PIPE --> OBJ
```

**Storage & governance notes**
- **Collection isolation:** one ChromaDB collection per repository; cross-repository leakage is impossible at query time because retrieval targets named collections under the caller's ACL.
- **Catalog keys:** PostgreSQL `documents` gains `repository` (financial · proposal · template) and `subtype` (e.g., annual_report, risk_assessment, pricing_template) so lineage and metrics can be sliced per repository.
- **Curation gate:** `repo_proposals` and `repo_templates` accept content only via approval; user uploads flow only into `repo_financial`.
- **Feedback loop:** approved generated proposals are re-ingested into `repo_proposals`, continuously enriching exemplars while preserving immutable audit lineage.
- **Backup/retention:** each collection is snapshotted independently; templates and curated proposals follow a slower, versioned change cadence than the higher-churn financial corpus.

---

*All other base-document sections (Layered Architecture, Security Architecture, Database ER model, LangGraph appendix) are unchanged except for the additive `repository`/`subtype` catalog columns noted above.*
