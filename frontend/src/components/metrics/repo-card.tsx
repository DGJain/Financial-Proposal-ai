import { cn } from "@/lib/utils/cn";

/**
 * RepoCard (ui-design.md §5.B) — an icon tile, a large display value, and a label.
 * The "Last Ingestion" date card uses `wide` for a smaller value.
 */
export function RepoCard({
  glyph,
  value,
  label,
  wide = false,
}: {
  glyph: string;
  value: string | number;
  label: string;
  wide?: boolean;
}) {
  return (
    <div className="rounded-xl border border-border bg-surface px-4 py-4">
      <span className="grid h-9 w-9 place-items-center rounded-lg bg-accent/15 text-accent">
        {glyph}
      </span>
      <p
        className={cn(
          "mt-3 font-semibold tabular-nums text-ink",
          wide ? "text-lg" : "text-3xl",
        )}
      >
        {value}
      </p>
      <p className="mt-0.5 text-xs text-muted">{label}</p>
    </div>
  );
}
