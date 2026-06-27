import { Badge, type Tone } from "@/components/ui/badge";
import type { RetrievalItem as RetrievalItemType } from "@/types/api";

const REPO_BADGE: Record<string, { label: string; tone: Tone }> = {
  financial: { label: "FIN", tone: "accent" },
  proposal: { label: "EX", tone: "success" },
  template: { label: "TPL", tone: "neutral" },
};

/**
 * One retrieved candidate (ui-design.md §5.C): a type badge, the source name, the
 * page span, and the cosine relevance score. Used in report sections §3/§4/§5.
 */
export function RetrievalItem({ item }: { item: RetrievalItemType }) {
  const badge = REPO_BADGE[item.repository] ?? { label: "DOC", tone: "neutral" as Tone };
  const pages =
    item.page_start === item.page_end
      ? `p.${item.page_start}`
      : `pp.${item.page_start}–${item.page_end}`;
  return (
    <div className="flex items-center gap-3 rounded-lg border border-border bg-surface-2 px-3 py-2">
      <Badge tone={badge.tone} className="w-12 justify-center font-mono">
        {badge.label}
      </Badge>
      <span className="flex-1 truncate text-sm text-ink">{item.source_name}</span>
      <span className="shrink-0 font-mono text-[11px] text-muted">{pages}</span>
      <span className="shrink-0 rounded bg-accent/15 px-2 py-0.5 font-mono text-[11px] text-accent">
        {item.score.toFixed(3)}
      </span>
    </div>
  );
}
