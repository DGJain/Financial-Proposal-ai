"use client";

import { useEffect, useState } from "react";

import { AnalyticsTable } from "@/components/analytics/analytics-table";
import { PageHeader } from "@/components/layout/page-header";
import { BarChartPanel } from "@/components/metrics/bar-chart-panel";
import { DonutPanel } from "@/components/metrics/donut-panel";
import { RepoCard } from "@/components/metrics/repo-card";
import { StatCard } from "@/components/metrics/stat-card";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ApiError,
  getGenerationHealth,
  getHistory,
  getRepositoryMetrics,
} from "@/lib/api-client/client";
import { asPct, formatDate } from "@/lib/utils/format";
import type {
  AnalyticsRow,
  GenerationHealth,
  RepositoryMetrics,
} from "@/types/api";

export default function MetricsPage() {
  const [repo, setRepo] = useState<RepositoryMetrics | null>(null);
  const [health, setHealth] = useState<GenerationHealth | null>(null);
  const [rows, setRows] = useState<AnalyticsRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    Promise.all([getRepositoryMetrics(), getGenerationHealth(7), getHistory(10, 0)])
      .then(([r, h, history]) => {
        if (!active) return;
        setRepo(r);
        setHealth(h);
        setRows(history.rows);
      })
      .catch((e) => {
        if (active) setError(e instanceof ApiError ? e.message : "Failed to load metrics.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  if (loading) {
    return (
      <div>
        <PageHeader title="Metrics" subtitle="Knowledge-base composition and generation health." />
        <p className="py-12 text-center text-sm text-muted">Loading metrics…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div>
        <PageHeader title="Metrics" subtitle="Knowledge-base composition and generation health." />
        <p className="py-12 text-center text-sm text-danger">{error}</p>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <PageHeader
        title="Metrics"
        subtitle="Knowledge-base composition and generation health."
      />

      {/* Zone 1 — repository composition */}
      {repo ? (
        <section>
          <h2 className="mb-3 text-xs font-medium uppercase tracking-wide text-muted">
            Repository composition
          </h2>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5">
            <RepoCard glyph="$" value={repo.financial_documents} label="Financial Documents" />
            <RepoCard glyph="✎" value={repo.proposal_examples} label="Proposal Examples" />
            <RepoCard glyph="▤" value={repo.templates} label="Templates" />
            <RepoCard glyph="◇" value={repo.embedded_chunks} label="Embedded Chunks" />
            <RepoCard
              glyph="◷"
              value={formatDate(repo.last_ingestion_ts)}
              label="Last Ingestion"
              wide
            />
          </div>
          <p className="mt-2 text-[11px] text-muted/80">
            Corpus contribution — financial {repo.corpus_contribution.financial.toFixed(1)}% ·
            proposal {repo.corpus_contribution.proposal.toFixed(1)}% · template{" "}
            {repo.corpus_contribution.template.toFixed(1)}%
          </p>
        </section>
      ) : null}

      {/* Zone 2 — generation health */}
      {health ? (
        <section>
          <h2 className="mb-3 text-xs font-medium uppercase tracking-wide text-muted">
            Generation health · last {health.window_days} days
          </h2>
          <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatCard
              label="Avg Confidence"
              value={health.avg_confidence.toFixed(2)}
              tone="quality"
            />
            <StatCard
              label="Avg Extraction"
              value={asPct(health.avg_extraction_quality)}
              tone="quality"
            />
            <StatCard
              label="Refusal Rate"
              value={asPct(health.refusal_rate)}
              tone={health.refusal_rate > 0.25 ? "loss" : "neutral"}
            />
            <StatCard
              label="Proposals"
              value={String(health.proposals_generated)}
              hint={`${health.runs_total} runs`}
              tone="accent"
            />
          </div>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <CardHeader>
                <CardTitle>Runs per day</CardTitle>
              </CardHeader>
              <CardBody>
                <BarChartPanel daily={health.daily} />
              </CardBody>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Information loss</CardTitle>
              </CardHeader>
              <CardBody>
                <DonutPanel buckets={health.info_loss_distribution} />
              </CardBody>
            </Card>
          </div>
        </section>
      ) : null}

      {/* Zone 3 — prompt-history analytics */}
      <section>
        <h2 className="mb-3 text-xs font-medium uppercase tracking-wide text-muted">
          Recent prompt analytics
        </h2>
        <Card>
          <CardBody>
            <AnalyticsTable rows={rows} context="dashboard" />
          </CardBody>
        </Card>
      </section>
    </div>
  );
}
