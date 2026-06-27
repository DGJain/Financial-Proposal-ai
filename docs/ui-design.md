# Frontend UI Architecture — Update 02 (Analytics & Execution Reporting)

*Addendum to `frontend-ui-architecture.md`. The sections below **supersede** their counterparts in the base spec. Companion prototype: `proposal-platform-ui.html` (Metrics → click any analytics row, or History → click any record, to open the Execution Report).*

---

## 2. Page Architecture — updated entries

### Page 3 · Proposal Preview *(constraint hardened)*
Unchanged layout (50/50 split, generated left / editable right). The editing contract is now explicit in the UI: the right pane is labelled **"text only · no structure · no template,"** and the footer reads **"Text-only editing · structure & template locked."** Headings, IDs, section order, and the underlying template are non-editable; only prose text within existing blocks can change. This keeps every sentence traceable and the chosen template intact for export.

### Page 4 · Metrics Dashboard *(expanded)*
Now three stacked zones:
1. **Repository cards** — composition of the private knowledge base.
2. **Generation health** — the existing grounding / extraction / refusal / proposals stat cards + 7-day chart + information-loss donut.
3. **Prompt History Analytics** — a per-prompt metrics table; each row is clickable and opens the Execution Report.

### Page 5 · Prompt History *(enriched + drill-in)*
The record list carries the full analytics field set (below), keeps search + status filters, and **every row opens a detailed Execution Report** at `/report/[id]` (or `/history/[id]`).

### Page 6 · Execution Report *(new — drill-in view)*
Not in the sidebar; reached only from a History or Analytics row. Full forensic breakdown of one prompt's run, with a Back control and the parent (History) nav item staying highlighted.

---

## 3. Component Hierarchy — updated branches

```
<MetricsDashboard>                       # EXPANDED
├── <RepositorySection>
│   └── <RepoCard×5/>                     # Financial Docs · Proposal Examples ·
│                                         #   Templates · Embedded Chunks · Last Ingestion
├── <GenerationHealthSection>
│   ├── <StatCard×4/>
│   ├── <BarChartPanel/>
│   └── <DonutPanel/>                     # information-loss distribution
└── <PromptHistoryAnalytics>             # NEW
    └── <AnalyticsTable onRowClick→report>
        └── <AnalyticsRow>                # 9 fields (see §5.A)
            ├── <PromptCell/> <Timestamp/> <FilesUsed/> <ProposalGenerated/>
            ├── <ProcessingTime/> <OcrMeter/> <ExtractionMeter/>
            └── <InfoLossMeter/> <RepoContribMeter/>

<PromptHistory>                          # ENRICHED
├── <SearchBar/> <FilterPills/>
└── <AnalyticsTable onRowClick→report>   # same component reused from dashboard
    └── <AnalyticsRow .../>

<ExecutionReport>                        # NEW VIEW
├── <ReportHeader> <BackButton/> <ReportId/>
├── <ReportStrip>                        # 4 headline metrics
│   └── <MetricCard ocr/ extraction/ infoLoss/ genTime/>
└── <ReportGrid>                         # 10 numbered sections
    ├── (1)  <PromptBlock/>
    ├── (2)  <UploadedFilesList> <RetrievalItem/>
    ├── (3)  <RetrievedFinancialDocs> <RetrievalItem score/>
    ├── (4)  <RetrievedProposalExamples> <RetrievalItem score/>
    ├── (5)  <RetrievedTemplates> <RetrievalItem score/>
    ├── (6·7)<QualityPanel> <QualityMeter ocr/coverage/table/overall/>
    ├── (8)  <InfoLossAnalysis> <QualityMeter ...> <GatePassBadge/>
    ├── (9)  <GenerationTimeline> <StageBar×5/>      # rewrite→retrieve→ground→generate→total
    └── (10) <CitationList> <CitationRow source page/>

Shared primitives added/reused:
  <RepoCard> <AnalyticsTable> <AnalyticsRow> <MiniMeter> (inline bar+value)
  <RetrievalItem> (icon · name · meta · relevance score)
  <StageBar> <CitationRow> <BackButton>
```

`<AnalyticsTable>` is a single shared component instantiated on both the Metrics Dashboard and the Prompt History page (same columns, same row-click → Execution Report), so the two pages never drift.

---

## 5. Design System — new component specs

**A. AnalyticsRow / AnalyticsTable** — 9-column dense grid, horizontally scrollable on narrow viewports (`min-width:1080px`). Columns:

| Field | Render |
|-------|--------|
| Prompt | title + proposal ID (mono) |
| Timestamp | `DD Mon · HH:MM` mono |
| Files Used | integer |
| Proposal Generated | ✓ Yes (green) / ◐ Draft (amber) / ✕ Refused (red) |
| Processing Time | seconds, mono |
| OCR Confidence | value + mini-meter (hi/mid/lo color) |
| Extraction Quality | value + mini-meter |
| Information Loss % | value + mini-meter (low = green) |
| Repository Contribution % | value + accent mini-meter (share of answer drawn from KB) |

Refused rows show `—` for OCR/extraction (no document stage ran) and 0% contribution.

**B. RepoCard** — icon tile + large display value + label. Five instances: **Financial Documents**, **Proposal Examples**, **Templates**, **Embedded Chunks**, **Last Ingestion Date** (the date card uses a smaller value via `.wide`).

**C. RetrievalItem** — type badge (DOC/XLS/EX/TPL) · name · meta (pages/sheets/"anonymized"/"structure locked") · relevance score chip (cosine similarity).

**D. MetricCard (report strip)** — uppercase label + large value, semantically colored (quality greens, neutral for time).

**E. StageBar** — labelled row with a proportional accent bar + mono duration; the timeline sums to the headline generation time.

Color semantics extend the base tokens: low information-loss = success (green), rising loss → warn → danger; repository-contribution bars use `--accent` (it is share, not quality).

---

## 6. UX Flows — updated & added

### 6.6 Prompt-history → execution-report drill-in *(new)*
```
Metrics Dashboard ─┐
                   ├─ click an analytics row ──► Execution Report (/report/[id])
Prompt History ────┘                              │
                                                  ├─ §1  Prompt (verbatim)
                                                  ├─ §2  Uploaded Files
                                                  ├─ §3  Retrieved Financial Documents (+scores)
                                                  ├─ §4  Retrieved Proposal Examples (+scores)
                                                  ├─ §5  Retrieved Templates (structure locked)
                                                  ├─ §6  OCR Confidence
                                                  ├─ §7  Extraction Quality
                                                  ├─ §8  Information-Loss Analysis (+gate verdict)
                                                  ├─ §9  Proposal Generation Time (stage timeline)
                                                  └─ §10 Retrieved Source Citations (source · page)
                                                  Back ──► returns to History (nav stays on History)
```
The report is **read-only and audit-linked** — it reconstructs exactly what the pipeline retrieved and produced for that prompt. A **Refused** record still opens a report: it shows the prompt, zero retrieved documents, the refusal reason, and no generation stages.

### 6.4 Edit + export flow *(amended)*
The editable pane permits prose changes within existing blocks only. Attempts to alter structure, reorder sections, or change the template are not exposed in the UI (no toolbar for them, headings non-editable). Export still renders the locked template with embedded lineage metadata; the information-loss gate continues to govern whether export is enabled.

### 6.7 Repository-composition view *(new, passive)*
On dashboard load, RepoCards read live counts from PostgreSQL/ChromaDB (financial docs, proposal examples, templates, embedded chunks) plus the last successful ingestion timestamp — giving operators an at-a-glance picture of corpus size and freshness before trusting generation metrics.

---

## 8. Build Notes — additions
- `<AnalyticsTable>` is one component; pass a `context="dashboard|history"` prop only for heading copy. Row click → `router.push('/report/'+id)`.
- Execution Report is a server component that hydrates from the audit/lineage store by `proposalId` (or `runId` for refusals) — it reads logged retrieval hits, scores, stage timings, and quality metrics; it computes nothing client-side.
- Repository counts and last-ingestion come from a lightweight `/metrics/repository` endpoint cached briefly in Redis.
- Keep mini-meters as a tiny presentational `<MiniMeter value tone>` primitive to avoid repeating bar markup across analytics, quality, and timeline sections.
