import { cn } from "@/lib/utils/cn";

type Tone = "quality" | "loss" | "accent" | "neutral";

const TONE_TEXT: Record<Tone, string> = {
  quality: "text-success",
  loss: "text-danger",
  accent: "text-accent",
  neutral: "text-ink",
};

/** A generation-health headline stat card (ui-design.md Page 4 §2). */
export function StatCard({
  label,
  value,
  hint,
  tone = "neutral",
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: Tone;
}) {
  return (
    <div className="rounded-xl border border-border bg-surface px-4 py-4">
      <p className="text-[10px] font-medium uppercase tracking-wide text-muted">{label}</p>
      <p className={cn("mt-1 text-2xl font-semibold tabular-nums", TONE_TEXT[tone])}>{value}</p>
      {hint ? <p className="mt-0.5 text-[11px] text-muted">{hint}</p> : null}
    </div>
  );
}
