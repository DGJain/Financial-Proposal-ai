/**
 * Shared enumerations — the exact value-level mirror of the backend domain
 * vocabulary (app/domain/**). String values MUST match the Python StrEnum
 * values so payloads round-trip without translation.
 *
 * Pattern: a frozen const object plus a same-named union type, giving both a
 * runtime value map and a compile-time type without TypeScript `enum` pitfalls.
 */

export const Repository = {
  Financial: 'financial',
  Proposal: 'proposal',
  Template: 'template',
} as const;
export type Repository = (typeof Repository)[keyof typeof Repository];

/** Canonical ChromaDB collection name per repository (source of truth). */
export const COLLECTION_NAMES: Readonly<Record<Repository, string>> = {
  [Repository.Financial]: 'repo_financial',
  [Repository.Proposal]: 'repo_proposals',
  [Repository.Template]: 'repo_templates',
} as const;

export const RoleInGeneration = {
  Evidence: 'evidence',
  Exemplar: 'exemplar',
  Scaffold: 'scaffold',
} as const;
export type RoleInGeneration = (typeof RoleInGeneration)[keyof typeof RoleInGeneration];

export const FileType = {
  Pdf: 'pdf',
  Docx: 'docx',
  Pptx: 'pptx',
  Png: 'png',
  Jpg: 'jpg',
} as const;
export type FileType = (typeof FileType)[keyof typeof FileType];

export const SensitivityFlag = {
  Pii: 'pii',
  Mnpi: 'mnpi',
} as const;
export type SensitivityFlag = (typeof SensitivityFlag)[keyof typeof SensitivityFlag];

export const ProposalStatus = {
  Draft: 'draft',
  Edited: 'edited',
  Approved: 'approved',
  Exported: 'exported',
} as const;
export type ProposalStatus = (typeof ProposalStatus)[keyof typeof ProposalStatus];

/**
 * Shown in Prompt History: ✓ generated · ◐ style-only · ◐ draft · ✕ refused.
 * `style_only` is the no-evidence fallback — a figure-free draft styled on past
 * proposals, with zero citations and LOW confidence.
 */
export const GenerationOutcome = {
  Generated: 'generated',
  StyleOnly: 'style_only',
  Draft: 'draft',
  Refused: 'refused',
} as const;
export type GenerationOutcome = (typeof GenerationOutcome)[keyof typeof GenerationOutcome];

export const Outcome = {
  Won: 'won',
  Lost: 'lost',
  Pending: 'pending',
} as const;
export type Outcome = (typeof Outcome)[keyof typeof Outcome];

export const ConfidenceBand = {
  High: 'high',
  Medium: 'medium',
  Low: 'low',
} as const;
export type ConfidenceBand = (typeof ConfidenceBand)[keyof typeof ConfidenceBand];

export const QualityGateVerdict = {
  Approved: 'approved',
  ReExtract: 're_extract',
  HumanReview: 'human_review',
} as const;
export type QualityGateVerdict = (typeof QualityGateVerdict)[keyof typeof QualityGateVerdict];

export const GenerationGateVerdict = {
  Pass: 'pass',
  BlockRegenerate: 'block_regenerate',
  Refuse: 'refuse',
} as const;
export type GenerationGateVerdict =
  (typeof GenerationGateVerdict)[keyof typeof GenerationGateVerdict];

/** Execution-report timeline stages: rewrite → retrieve → ground → generate (+ total). */
export const GenerationStage = {
  Rewrite: 'rewrite',
  Retrieve: 'retrieve',
  Ground: 'ground',
  Generate: 'generate',
  Total: 'total',
} as const;
export type GenerationStage = (typeof GenerationStage)[keyof typeof GenerationStage];

/** Atomic kind of a chunk's payload — financial chunking keeps tables/figures atomic. */
export const ContentType = {
  Text: 'text',
  Table: 'table',
  Figure: 'figure',
} as const;
export type ContentType = (typeof ContentType)[keyof typeof ContentType];

/** Terminal outcome of one ingestion run (upload status surfaced to the UI). */
export const IngestionStatus = {
  Indexed: 'indexed',
  SkippedDuplicate: 'skipped_duplicate',
  RoutedToReview: 'routed_to_review',
} as const;
export type IngestionStatus = (typeof IngestionStatus)[keyof typeof IngestionStatus];

/** Why a document was routed to human review instead of indexed. */
export const ReviewReason = {
  LowClassifierConfidence: 'low_classifier_confidence',
  QualityGateFailed: 'quality_gate_failed',
  AnonymizationFailed: 'anonymization_failed',
  NotCurated: 'not_curated',
} as const;
export type ReviewReason = (typeof ReviewReason)[keyof typeof ReviewReason];

/** Categories of residual sensitive content the curation gate blocks on. */
export const AnonymizationFindingKind = {
  HardFigure: 'hard_figure',
  ResidualPii: 'residual_pii',
  ResidualMnpi: 'residual_mnpi',
  ClientIdentifier: 'client_identifier',
} as const;
export type AnonymizationFindingKind =
  (typeof AnonymizationFindingKind)[keyof typeof AnonymizationFindingKind];

/** Sensitive content categories removed by the redaction stage. */
export const RedactionKind = {
  Pii: 'pii',
  Mnpi: 'mnpi',
} as const;
export type RedactionKind = (typeof RedactionKind)[keyof typeof RedactionKind];

export const Modality = {
  Text: 'text',
  Ocr: 'ocr',
  Table: 'table',
  Figure: 'figure',
  Meta: 'meta',
  Entity: 'entity',
  SemanticRetention: 'semantic_retention',
  Structure: 'structure',
} as const;
export type Modality = (typeof Modality)[keyof typeof Modality];
