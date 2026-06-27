import type { DailyBar } from "@/types/api";

/**
 * A dependency-free per-day run chart (ui-design.md Page 4 §2): one column per day
 * in the window, stacking generated (accent) over refused (danger). Heights are
 * proportional to the busiest day.
 */
export function BarChartPanel({ daily }: { daily: DailyBar[] }) {
  const max = Math.max(1, ...daily.map((d) => d.generated + d.refused));
  return (
    <div className="flex h-40 items-end gap-2">
      {daily.map((d) => {
        const total = d.generated + d.refused;
        const genH = (d.generated / max) * 100;
        const refH = (d.refused / max) * 100;
        const dayLabel = new Date(d.day).getDate();
        return (
          <div key={d.day} className="flex flex-1 flex-col items-center gap-1">
            <div
              className="flex w-full max-w-[2.5rem] flex-col justify-end rounded-md bg-surface-2"
              style={{ height: "8rem" }}
              title={`${d.day}: ${d.generated} generated, ${d.refused} refused`}
            >
              {refH > 0 ? (
                <div className="w-full rounded-t-md bg-danger" style={{ height: `${refH}%` }} />
              ) : null}
              {genH > 0 ? (
                <div
                  className="w-full bg-accent"
                  style={{ height: `${genH}%`, borderTopLeftRadius: refH > 0 ? 0 : 6, borderTopRightRadius: refH > 0 ? 0 : 6 }}
                />
              ) : null}
            </div>
            <span className="text-[10px] tabular-nums text-muted">{total > 0 ? total : ""}</span>
            <span className="text-[10px] text-muted/70">{dayLabel}</span>
          </div>
        );
      })}
    </div>
  );
}
