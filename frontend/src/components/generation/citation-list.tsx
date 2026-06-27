import type { Citation } from "@/types/api";

export function CitationList({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) {
    return <p className="text-sm text-muted">No citations.</p>;
  }
  return (
    <ul className="space-y-1.5">
      {citations.map((c) => (
        <li
          key={`${c.claim_ordinal}-${c.source_name}-${c.page}`}
          className="flex items-center gap-3 rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm"
        >
          <span className="grid h-6 w-8 shrink-0 place-items-center rounded bg-accent/15 font-mono text-[11px] text-accent">
            F{c.claim_ordinal + 1}
          </span>
          <span className="flex-1 truncate text-ink">{c.source_name}</span>
          <span className="shrink-0 font-mono text-xs text-muted">p.{c.page}</span>
        </li>
      ))}
    </ul>
  );
}
