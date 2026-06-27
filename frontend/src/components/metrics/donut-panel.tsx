import type { InfoLossBucket } from "@/types/api";

const BUCKET = {
  low: { color: "#22c55e", label: "Low (<5%)" },
  medium: { color: "#f59e0b", label: "Medium (5–10%)" },
  high: { color: "#ef4444", label: "High (>10%)" },
} as const;

/**
 * Information-loss distribution donut (ui-design.md Page 4 §2) — a dependency-free
 * conic-gradient ring over the low/medium/high buckets of retrieved evidence loss.
 */
export function DonutPanel({ buckets }: { buckets: InfoLossBucket[] }) {
  const total = buckets.reduce((sum, b) => sum + b.count, 0);
  let acc = 0;
  const stops = buckets
    .map((b) => {
      const start = total > 0 ? (acc / total) * 360 : 0;
      acc += b.count;
      const end = total > 0 ? (acc / total) * 360 : 0;
      const color = BUCKET[b.label as keyof typeof BUCKET]?.color ?? "#64748b";
      return `${color} ${start}deg ${end}deg`;
    })
    .join(", ");
  const background =
    total > 0 ? `conic-gradient(${stops})` : "conic-gradient(#1f2937 0deg 360deg)";

  return (
    <div className="flex items-center gap-6">
      <div
        className="relative h-28 w-28 shrink-0 rounded-full"
        style={{ background }}
        aria-label="information loss distribution"
      >
        <div className="absolute inset-[22%] grid place-items-center rounded-full bg-surface">
          <span className="text-lg font-semibold tabular-nums text-ink">{total}</span>
        </div>
      </div>
      <ul className="space-y-1.5 text-sm">
        {buckets.map((b) => {
          const meta = BUCKET[b.label as keyof typeof BUCKET];
          return (
            <li key={b.label} className="flex items-center gap-2">
              <span
                className="h-2.5 w-2.5 rounded-full"
                style={{ backgroundColor: meta?.color ?? "#64748b" }}
              />
              <span className="text-muted">{meta?.label ?? b.label}</span>
              <span className="font-mono text-xs text-ink">{b.count}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
