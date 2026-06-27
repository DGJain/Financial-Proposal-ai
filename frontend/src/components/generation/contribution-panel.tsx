import { MiniMeter } from "@/components/ui/meter";
import type { Contribution } from "@/types/api";

/**
 * Dual repository contribution (rag-design.md §6b): context share = how much each
 * repository shaped the input; factual share = how much factual weight it carried.
 * Healthy factual share is ~100% financial — the leakage guardrail depends on it.
 */
export function ContributionPanel({ contribution }: { contribution: Contribution }) {
  const { context_share, factual_share } = contribution;
  return (
    <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
      <div>
        <p className="mb-3 text-xs font-medium uppercase tracking-wide text-muted">
          Context contribution
        </p>
        <div className="space-y-2">
          <MiniMeter label="Financial" value={context_share.financial} tone="accent" />
          <MiniMeter label="Proposal" value={context_share.proposal} tone="accent" />
          <MiniMeter label="Template" value={context_share.template} tone="accent" />
        </div>
      </div>
      <div>
        <p className="mb-3 text-xs font-medium uppercase tracking-wide text-muted">
          Factual contribution
        </p>
        <div className="space-y-2">
          <MiniMeter label="Financial" value={factual_share.financial} tone="quality" />
          <MiniMeter label="Proposal" value={factual_share.proposal} tone="loss" />
          <MiniMeter label="Template" value={factual_share.template} tone="loss" />
        </div>
        <p className="mt-2 text-[11px] text-muted/80">
          Non-financial factual weight signals figure leakage — it is blocked, not shown.
        </p>
      </div>
    </div>
  );
}
