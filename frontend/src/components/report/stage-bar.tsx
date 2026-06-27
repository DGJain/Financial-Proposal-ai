import { cn } from "@/lib/utils/cn";
import type { StageTiming } from "@/types/api";

const STAGE_LABEL: Record<string, string> = {
  rewrite: "Rewrite",
  retrieve: "Retrieve",
  ground: "Ground",
  generate: "Generate",
  total: "Total",
};

/**
 * StageBar (ui-design.md §5.E): a labelled row with a proportional accent bar and
 * a mono duration. The four pipeline stages sum to the headline TOTAL.
 */
export function StageBar({ timing, max }: { timing: StageTiming; max: number }) {
  const isTotal = timing.stage === "total";
  const pct = max > 0 ? Math.min(100, (timing.duration_ms / max) * 100) : 0;
  return (
    <div className="flex items-center gap-3">
      <span className={cn("w-20 shrink-0 text-xs", isTotal ? "font-semibold text-ink" : "text-muted")}>
        {STAGE_LABEL[timing.stage] ?? timing.stage}
      </span>
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-2">
        <div
          className={cn("h-full rounded-full", isTotal ? "bg-ink/40" : "bg-accent")}
          style={{ width: `${isTotal ? 100 : pct}%` }}
        />
      </div>
      <span className="w-16 shrink-0 text-right font-mono text-[11px] text-ink">
        {timing.duration_ms} ms
      </span>
    </div>
  );
}
