import { cn } from "@/lib/utils/cn";

type Tone = "quality" | "loss" | "accent";

/**
 * MiniMeter — a tiny inline bar + value, reused across contribution, quality, and
 * timeline rows. ``quality`` greens at high values; ``loss`` greens at *low*
 * values (low information loss is good); ``accent`` is neutral share, not quality.
 */
export function MiniMeter({
  value,
  max = 100,
  tone = "accent",
  label,
}: {
  value: number;
  max?: number;
  tone?: Tone;
  label?: string;
}) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  const color = barColor(tone, pct);
  return (
    <div className="flex items-center gap-2">
      {label ? <span className="w-20 shrink-0 text-[11px] text-muted">{label}</span> : null}
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2">
        <div className={cn("h-full rounded-full transition-all", color)} style={{ width: `${pct}%` }} />
      </div>
      <span className="w-12 shrink-0 text-right font-mono text-[11px] text-ink">
        {value.toFixed(1)}%
      </span>
    </div>
  );
}

function barColor(tone: Tone, pct: number): string {
  if (tone === "accent") return "bg-accent";
  if (tone === "loss") {
    if (pct < 20) return "bg-success";
    if (pct < 50) return "bg-warn";
    return "bg-danger";
  }
  // quality
  if (pct >= 80) return "bg-success";
  if (pct >= 50) return "bg-warn";
  return "bg-danger";
}
