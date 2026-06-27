"use client";

import { useEffect, useMemo, useState } from "react";

import { AnalyticsTable } from "@/components/analytics/analytics-table";
import { PageHeader } from "@/components/layout/page-header";
import { Card, CardBody } from "@/components/ui/card";
import { cn } from "@/lib/utils/cn";
import { ApiError, getHistory } from "@/lib/api-client/client";
import type { AnalyticsRow, GenerationOutcome } from "@/types/api";

type Filter = "all" | GenerationOutcome;

const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "generated", label: "Generated" },
  { key: "style_only", label: "Style-only" },
  { key: "draft", label: "Draft" },
  { key: "refused", label: "Refused" },
];

export default function HistoryPage() {
  const [rows, setRows] = useState<AnalyticsRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");

  useEffect(() => {
    let active = true;
    setLoading(true);
    getHistory(100, 0)
      .then((data) => {
        if (active) setRows(data.rows);
      })
      .catch((e) => {
        if (active) setError(e instanceof ApiError ? e.message : "Failed to load history.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return rows.filter((r) => {
      if (filter !== "all" && r.outcome !== filter) return false;
      if (!q) return true;
      return (
        r.title.toLowerCase().includes(q) ||
        (r.proposal_id ?? r.gen_id).toLowerCase().includes(q)
      );
    });
  }, [rows, query, filter]);

  return (
    <div>
      <PageHeader
        title="Prompt History"
        subtitle="Every generation run, newest first. Open any row for its Execution Report."
      />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search prompt or proposal id…"
          className="w-72 rounded-lg border border-border bg-surface px-3 py-2 text-sm text-ink outline-none placeholder:text-muted/60 focus:border-accent"
        />
        <div className="flex gap-1.5">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              type="button"
              onClick={() => setFilter(f.key)}
              className={cn(
                "rounded-full border px-3 py-1 text-xs transition-colors",
                filter === f.key
                  ? "border-accent/40 bg-accent/15 text-accent"
                  : "border-border text-muted hover:text-ink",
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      <Card>
        <CardBody>
          {loading ? (
            <p className="py-8 text-center text-sm text-muted">Loading history…</p>
          ) : error ? (
            <p className="py-8 text-center text-sm text-danger">{error}</p>
          ) : (
            <AnalyticsTable rows={visible} context="history" />
          )}
        </CardBody>
      </Card>
    </div>
  );
}
