/**
 * Metrics & dashboard contract shapes (ui-design.md §2/§5, rag-design.md §6).
 * Percentages are 0–100 numbers; the two contribution families each sum to ~100.
 */

import type { GenerationOutcome, Repository } from '../enums/index.js';

/** A per-repository percentage triple summing to ~100 (0 for refused runs). */
export interface RepositoryShare {
  financial: number;
  proposal: number;
  template: number;
}

export interface ContributionBreakdown {
  /** How much each repository shaped the assembled context. */
  contextShare: RepositoryShare;
  /** Lineage-based share of grounded claims cited per repository (~100% financial). */
  factualShare: RepositoryShare;
}

/** Repository cards on the dashboard (live counts + freshness). */
export interface RepositoryCardMetrics {
  financialDocuments: number;
  proposalExamples: number;
  templates: number;
  embeddedChunks: number;
  lastIngestionDate: string | null;
}

/** One row of the Prompt-History analytics table (9-field set). */
export interface AnalyticsRow {
  id: string;
  promptTitle: string;
  proposalId: string | null;
  timestamp: string;
  filesUsed: number;
  proposalGenerated: GenerationOutcome;
  processingTimeSeconds: number;
  ocrConfidence: number | null;
  extractionQuality: number | null;
  informationLossPct: number | null;
  repositoryContributionPct: number;
}

/** Generation-health summary cards + trend window. */
export interface GenerationHealth {
  groundingRate: number;
  extractionQuality: number;
  refusalRate: number;
  proposalsGenerated: number;
  informationLossDistribution: Record<Repository, number>;
}
