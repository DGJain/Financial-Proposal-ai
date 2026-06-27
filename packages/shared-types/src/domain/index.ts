/**
 * Domain contract shapes — the structural mirror of app/domain/** entities and
 * value objects. Timestamps are ISO-8601 strings; numeric scores are in [0, 1]
 * unless a field name ends in `Pct`.
 */

import type {
  ConfidenceBand,
  FileType,
  GenerationGateVerdict,
  GenerationOutcome,
  GenerationStage,
  ProposalStatus,
  Repository,
  RoleInGeneration,
  SensitivityFlag,
} from '../enums/index.js';

/** Classifier soft distribution π_d = (π_FIN, π_PROP, π_TMPL), Σ = 1. */
export interface SoftDistribution {
  financial: number;
  proposal: number;
  template: number;
}

/** Access-control requirements carried from ingestion into every retrieval. */
export interface AccessControl {
  aclGroups: string[];
  engagementId: string | null;
  classification: string | null;
}

export interface Provenance {
  sourceUri: string;
  fileType: FileType;
  ingestionTs: string;
  pageCount: number;
  language: string;
  contentHash: string;
}

export interface Document {
  docId: string;
  repository: Repository;
  subtype: string;
  provenance: Provenance;
  access: AccessControl;
  softDistribution: SoftDistribution;
  repoConfidence: number;
  sensitivity: SensitivityFlag[];
  objectUriVersioned: string | null;
  lineageRoot: string | null;
  parentDocId: string | null;
  version: number;
}

export interface ChunkSpan {
  pageStart: number;
  pageEnd: number;
  bbox: [number, number, number, number] | null;
}

export interface QualityScores {
  eqs: number;
  ocrConfidence: number;
  cfr: number | null;
  rpr: number | null;
  hasCriticalLowConfidenceRegion: boolean;
  sectionCoverage: number | null;
  placeholderIntegrity: number | null;
  structuralFidelity: number | null;
  classificationConfidence: number | null;
  /** Headline information-loss %, = (1 − eqs) × 100. */
  informationLossPct: number;
}

export interface Chunk {
  chunkId: string;
  docId: string;
  repository: Repository;
  roleInGeneration: RoleInGeneration;
  text: string;
  ordinal: number;
  span: ChunkSpan;
  embeddingModelVersion: string;
  vectorId: string | null;
  metadata: Record<string, unknown>;
}

/** One section of a proposal; heading/id/order/slot are structural & locked. */
export interface ProposalSection {
  sectionId: string;
  slot: string;
  heading: string;
  order: number;
  body: string;
}

export interface ProposalVersion {
  versionNo: number;
  sections: ProposalSection[];
  createdTs: string;
  createdBy: string;
  status: ProposalStatus;
}

export interface Proposal {
  proposalId: string;
  genId: string;
  engagementId: string;
  templateId: string;
  versions: ProposalVersion[];
  status: ProposalStatus;
}

// --- Generation lineage (backs the Execution Report) -------------------------

export interface RetrievalHit {
  chunkId: string;
  docId: string;
  repository: Repository;
  score: number;
  sourceName: string;
  pageStart: number;
  pageEnd: number;
}

export interface Citation {
  claimOrdinal: number;
  chunkId: string;
  repository: Repository;
  sourceName: string;
  page: number;
}

export interface StageTiming {
  stage: GenerationStage;
  durationMs: number;
}

export interface GateOutcome {
  name: string;
  verdict: GenerationGateVerdict;
  detail: string | null;
}

export interface GenerationEvent {
  genId: string;
  engagementId: string;
  prompt: string;
  ts: string;
  outcome: GenerationOutcome;
  confidence: number;
  confidenceBand: ConfidenceBand;
  retrievalHits: RetrievalHit[];
  citations: Citation[];
  stageTimings: StageTiming[];
  gateOutcomes: GateOutcome[];
  proposalId: string | null;
  refusalReason: string | null;
  policyFingerprint: string | null;
}
