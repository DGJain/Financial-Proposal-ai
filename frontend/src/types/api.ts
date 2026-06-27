/**
 * Wire types — the value-level mirror of the backend's API DTOs
 * (`app/api/schemas/generation.py`). String enum values MUST match the Python
 * StrEnum values so payloads round-trip without translation, exactly as
 * `packages/shared-types` mirrors the domain vocabulary.
 */

export type Repository = "financial" | "proposal" | "template";

export type GenerationOutcome = "generated" | "style_only" | "draft" | "refused";

export type ConfidenceBand = "high" | "medium" | "low";

export type ProposalStatus = "draft" | "edited" | "approved" | "exported";

export type FileType = "pdf" | "docx" | "pptx" | "png" | "jpg";

export interface RepositoryShare {
  financial: number;
  proposal: number;
  template: number;
}

export interface Contribution {
  context_share: RepositoryShare;
  factual_share: RepositoryShare;
}

export interface Confidence {
  score: number;
  band: ConfidenceBand;
}

export interface Citation {
  claim_ordinal: number;
  source_name: string;
  page: number;
}

export interface Section {
  section_id: string;
  slot: string;
  heading: string;
  order: number;
  body: string;
}

export interface Proposal {
  proposal_id: string;
  gen_id: string;
  engagement_id: string;
  template_id: string;
  status: ProposalStatus;
  version_no: number;
  sections: Section[];
}

export interface Attachment {
  name: string;
  text: string;
}

/** Server-side extraction result for one uploaded binary (PDF/DOCX/PPTX/image). */
export interface AttachmentExtraction {
  name: string;
  text: string;
  extracted: boolean;
  char_count: number;
  detail: string;
}

export interface GenerateRequest {
  title: string;
  proposal_type: string;
  entity?: string | null;
  fiscal_year?: number | null;
  sector?: string | null;
  line_items: string[];
  instructions?: string;
  query?: string;
  attachments?: Attachment[];
}

export interface GenerateResponse {
  report_id: string;
  outcome: GenerationOutcome;
  confidence: Confidence;
  contribution: Contribution | null;
  citations: Citation[];
  proposal: Proposal | null;
  refusal_reason: string | null;
}

export interface SectionEdit {
  section_id: string;
  body: string;
}

export interface EditRequest {
  edits: SectionEdit[];
}

/** The caller's ACL/engagement context, forwarded to the backend as X-* headers. */
export interface RequesterContext {
  engagementId?: string;
  aclGroups?: string;
  classification?: string;
  requestedBy?: string;
}

export interface IngestResponse {
  status: string;
  doc_id: string;
  repository: Repository;
  chunk_count: number;
  gate_verdict?: string;
  review_reason?: string;
}

// --- Phase 5: analytics / reporting (app/api/schemas/analytics.py) -----------

export type GateVerdict = "approved" | "re_extract" | "human_review";

export type GenerationStage = "rewrite" | "retrieve" | "ground" | "generate" | "total";

export interface RetrievalItem {
  chunk_id: string;
  doc_id: string;
  repository: Repository;
  source_name: string;
  score: number;
  page_start: number;
  page_end: number;
}

export interface StageTiming {
  stage: GenerationStage;
  duration_ms: number;
}

export interface ReportCitation {
  claim_ordinal: number;
  source_name: string;
  page: number;
}

export interface RunQuality {
  ocr_confidence: number;
  extraction_quality: number;
  information_loss_pct: number;
  gate_verdict: GateVerdict;
  document_count: number;
}

/** The Execution Report — 10 numbered sections for one run (ui-design.md §6.6). */
export interface ExecutionReport {
  gen_id: string;
  prompt: string;
  engagement_id: string;
  timestamp: string;
  outcome: GenerationOutcome;
  confidence: Confidence;
  proposal_id: string | null;
  refusal_reason: string | null;
  files_used: string[];
  retrieved_financial: RetrievalItem[];
  retrieved_proposal: RetrievalItem[];
  retrieved_template: RetrievalItem[];
  quality: RunQuality | null;
  stages: StageTiming[];
  total_duration_ms: number;
  citations: ReportCitation[];
  contribution: Contribution | null;
}

/** A nine-field prompt-history / analytics row (ui-design.md §5.A). */
export interface AnalyticsRow {
  gen_id: string;
  proposal_id: string | null;
  title: string;
  timestamp: string;
  files_used: number;
  outcome: GenerationOutcome;
  processing_time_s: number;
  ocr_confidence: number | null;
  extraction_quality: number | null;
  information_loss_pct: number | null;
  repository_contribution_pct: number;
}

export interface PromptHistory {
  rows: AnalyticsRow[];
  limit: number;
  offset: number;
}

export interface RepositoryMetrics {
  financial_documents: number;
  proposal_examples: number;
  templates: number;
  embedded_chunks: number;
  last_ingestion_ts: string | null;
  corpus_contribution: RepositoryShare;
}

export interface DailyBar {
  day: string;
  generated: number;
  refused: number;
}

export interface InfoLossBucket {
  label: string;
  count: number;
}

export interface GenerationHealth {
  window_days: number;
  runs_total: number;
  proposals_generated: number;
  refusal_rate: number;
  avg_confidence: number;
  avg_extraction_quality: number;
  daily: DailyBar[];
  info_loss_distribution: InfoLossBucket[];
}

export interface Health {
  status: string;
  service: string;
  version: string;
  environment: string;
  air_gapped: boolean;
  model_provider: string;
  llm_model_id: string;
  embedding_model_version: string;
}

export type ExportFormat = "markdown" | "html" | "pdf" | "docx";
