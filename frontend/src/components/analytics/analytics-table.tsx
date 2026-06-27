"use client";

import { useRouter } from "next/navigation";

import { Badge, type Tone } from "@/components/ui/badge";
import { MiniMeter } from "@/components/ui/meter";
import { formatTimestamp } from "@/lib/utils/format";
import type { AnalyticsRow, GenerationOutcome } from "@/types/api";

const OUTCOME: Record<GenerationOutcome, { glyph: string; label: string; tone: Tone }> = {
  generated: { glyph: "✓", label: "Yes", tone: "success" },
  style_only: { glyph: "◐", label: "Style-only", tone: "warn" },
  draft: { glyph: "◐", label: "Draft", tone: "warn" },
  refused: { glyph: "✕", label: "Refused", tone: "danger" },
};

const COLUMNS = [
  "Prompt",
  "Timestamp",
  "Files",
  "Proposal",
  "Time",
  "OCR Confidence",
  "Extraction Quality",
  "Information Loss",
  "Repository Contribution",
];

/**
 * The single analytics table shared by the Metrics Dashboard and Prompt History
 * (ui-design.md §3/§5.A) — one shape so the two surfaces never drift. Each row
 * opens the Execution Report for its run.
 */
export function AnalyticsTable({
  rows,
  context,
}: {
  rows: AnalyticsRow[];
  context: "dashboard" | "history";
}) {
  const router = useRouter();

  if (rows.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-border px-4 py-8 text-center text-sm text-muted">
        {context === "history"
          ? "No runs match your filters yet."
          : "No generation runs recorded yet."}
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[1080px] border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-[11px] uppercase tracking-wide text-muted">
            {COLUMNS.map((c) => (
              <th key={c} className="px-3 py-2 font-medium">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const outcome = OUTCOME[row.outcome];
            return (
              <tr
                key={row.gen_id}
                onClick={() => router.push(`/report/${row.gen_id}`)}
                className="cursor-pointer border-b border-border/60 transition-colors hover:bg-surface-2"
              >
                <td className="px-3 py-2.5">
                  <p className="max-w-xs truncate font-medium text-ink">{row.title}</p>
                  <p className="font-mono text-[11px] text-muted">
                    {row.proposal_id ?? row.gen_id}
                  </p>
                </td>
                <td className="whitespace-nowrap px-3 py-2.5 font-mono text-[11px] text-muted">
                  {formatTimestamp(row.timestamp)}
                </td>
                <td className="px-3 py-2.5 tabular-nums text-ink">{row.files_used}</td>
                <td className="px-3 py-2.5">
                  <Badge tone={outcome.tone}>
                    <span>{outcome.glyph}</span>
                    {outcome.label}
                  </Badge>
                </td>
                <td className="whitespace-nowrap px-3 py-2.5 font-mono text-[11px] text-ink">
                  {row.processing_time_s.toFixed(2)} s
                </td>
                <td className="px-3 py-2.5">
                  <QualityCell value={row.ocr_confidence} tone="quality" scale={100} />
                </td>
                <td className="px-3 py-2.5">
                  <QualityCell value={row.extraction_quality} tone="quality" scale={100} />
                </td>
                <td className="px-3 py-2.5">
                  {row.information_loss_pct === null ? (
                    <Dash />
                  ) : (
                    <MiniMeter value={row.information_loss_pct} tone="loss" />
                  )}
                </td>
                <td className="px-3 py-2.5">
                  <MiniMeter value={row.repository_contribution_pct} tone="accent" />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function QualityCell({
  value,
  tone,
  scale,
}: {
  value: number | null;
  tone: "quality" | "loss" | "accent";
  scale: number;
}) {
  if (value === null) return <Dash />;
  return <MiniMeter value={value * scale} tone={tone} />;
}

function Dash() {
  return <span className="font-mono text-xs text-muted/60">—</span>;
}
