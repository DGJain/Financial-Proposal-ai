import { cn } from "@/lib/utils/cn";

type Tone = "quality" | "loss" | "neutral";

const TONE_TEXT: Record<Tone, string> = {
  quality: "text-success",
  loss: "text-warn",
  neutral: "text-ink",
};

/**
 * MetricCard (ui-design.md §5.D) — the report strip's headline tiles: an uppercase
 * label and a large, semantically coloured value (quality greens, neutral time).
 */
export function MetricCard({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string;
  tone?: Tone;
}) {
  return (
    <div className="rounded-xl border border-border bg-surface px-4 py-3">
      <p className="text-[10px] font-medium uppercase tracking-wide text-muted">{label}</p>
      <p className={cn("mt-1 text-2xl font-semibold tabular-nums", TONE_TEXT[tone])}>{value}</p>
    </div>
  );
}
