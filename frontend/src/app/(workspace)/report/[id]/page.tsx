"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { CitationList } from "@/components/generation/citation-list";
import { ConfidenceBadge } from "@/components/generation/confidence-badge";
import { ContributionPanel } from "@/components/generation/contribution-panel";
import { MetricCard } from "@/components/report/metric-card";
import { RetrievalItem } from "@/components/report/retrieval-item";
import { StageBar } from "@/components/report/stage-bar";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError, exportProposalUrl, getExecutionReport } from "@/lib/api-client/client";
import { asPct, formatTimestamp } from "@/lib/utils/format";
import type { ExecutionReport, RetrievalItem as RetrievalItemType } from "@/types/api";

export default function ReportPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const genId = params.id;
  const [report, setReport] = useState<ExecutionReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    getExecutionReport(genId)
      .then((data) => {
        if (active) setReport(data);
      })
      .catch((e) => {
        if (active) setError(e instanceof ApiError ? e.message : "Failed to load report.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [genId]);

  return (
    <div>
      <div className="mb-6 flex items-center justify-between gap-4">
        <button
          type="button"
          onClick={() => router.back()}
          className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-sm text-muted transition-colors hover:text-ink"
        >
          ← Back
        </button>
        <span className="font-mono text-xs text-muted">{genId}</span>
      </div>

      {loading ? (
        <p className="py-12 text-center text-sm text-muted">Loading report…</p>
      ) : error ? (
        <p className="py-12 text-center text-sm text-danger">{error}</p>
      ) : report ? (
        <ReportBody report={report} />
      ) : null}
    </div>
  );
}

function ReportBody({ report }: { report: ExecutionReport }) {
  const refused = report.outcome === "refused";
  const styleOnly = report.outcome === "style_only";
  const q = report.quality;

  return (
    <div className="space-y-5">
      {/* header */}
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold tracking-tight text-ink">Execution Report</h1>
        <Badge tone={refused ? "danger" : styleOnly ? "warn" : "success"}>
          {refused ? "✕ Refused" : styleOnly ? "◐ Style-only" : "✓ Generated"}
        </Badge>
        <ConfidenceBadge band={report.confidence.band} score={report.confidence.score} />
        <span className="text-xs text-muted">{formatTimestamp(report.timestamp)}</span>
        {report.proposal_id && !refused ? (
          <div className="ml-auto flex items-center gap-2">
            <Link
              href={`/preview/${report.proposal_id}`}
              className="rounded-lg border border-border px-3 py-1.5 text-xs text-muted hover:text-ink"
            >
              Preview
            </Link>
            <a
              href={exportProposalUrl(report.proposal_id, "pdf")}
              target="_blank"
              rel="noreferrer"
              className="rounded-lg border border-accent/40 bg-accent/15 px-3 py-1.5 text-xs text-accent"
            >
              Export PDF
            </a>
            <a
              href={exportProposalUrl(report.proposal_id, "docx")}
              target="_blank"
              rel="noreferrer"
              className="rounded-lg border border-border px-3 py-1.5 text-xs text-muted hover:text-ink"
            >
              Export DOCX
            </a>
          </div>
        ) : null}
      </div>

      {/* report strip */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <MetricCard label="OCR Confidence" value={asPct(q?.ocr_confidence)} tone="quality" />
        <MetricCard label="Extraction Quality" value={asPct(q?.extraction_quality)} tone="quality" />
        <MetricCard
          label="Information Loss"
          value={q ? `${q.information_loss_pct.toFixed(1)}%` : "—"}
          tone="loss"
        />
        <MetricCard label="Generation Time" value={`${report.total_duration_ms} ms`} />
      </div>

      {/* §1 prompt */}
      <Section n={1} title="Prompt">
        <p className="whitespace-pre-wrap rounded-lg border border-border bg-surface-2 px-4 py-3 text-sm text-ink">
          {report.prompt}
        </p>
        {refused && report.refusal_reason ? (
          <p className="mt-3 rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
            Refused — {report.refusal_reason}
          </p>
        ) : null}
        {styleOnly ? (
          <p className="mt-3 rounded-lg border border-warn/30 bg-warn/10 px-4 py-3 text-sm text-warn">
            Style-only draft — no financial evidence cleared the grounding floor, so
            this proposal follows the template and past-proposal style with no figures
            and no citations.
          </p>
        ) : null}
      </Section>

      {/* §2 files used */}
      <Section n={2} title="Uploaded / Source Files">
        {report.files_used.length === 0 ? (
          <Empty>No documents were retrieved.</Empty>
        ) : (
          <ul className="flex flex-wrap gap-2">
            {report.files_used.map((f) => (
              <li key={f} className="rounded-lg border border-border bg-surface-2 px-3 py-1.5 text-xs text-ink">
                {f}
              </li>
            ))}
          </ul>
        )}
      </Section>

      {/* §3/§4/§5 retrieved by repository */}
      <RetrievalSection n={3} title="Retrieved Financial Documents" items={report.retrieved_financial} />
      <RetrievalSection n={4} title="Retrieved Proposal Examples" items={report.retrieved_proposal} />
      <RetrievalSection n={5} title="Retrieved Templates" items={report.retrieved_template} />

      {/* §6/7/8 quality + gate */}
      <Section n={6} title="Evidence Quality & Information Loss">
        {q ? (
          <div className="space-y-3">
            <QualityRow label="OCR confidence" value={asPct(q.ocr_confidence)} />
            <QualityRow label="Extraction quality" value={asPct(q.extraction_quality)} />
            <QualityRow label="Information loss" value={`${q.information_loss_pct.toFixed(1)}%`} />
            <div className="flex items-center gap-3 pt-1">
              <span className="text-sm text-muted">Evidence gate</span>
              <Badge tone={q.gate_verdict === "approved" ? "success" : "warn"}>
                {q.gate_verdict}
              </Badge>
              <span className="text-[11px] text-muted">
                across {q.document_count} financial document{q.document_count === 1 ? "" : "s"}
              </span>
            </div>
          </div>
        ) : (
          <Empty>No financial evidence stage ran for this prompt.</Empty>
        )}
      </Section>

      {/* §9 timeline */}
      <Section n={9} title="Generation Timeline">
        {report.stages.length === 0 ? (
          <Empty>No generation stages — the run was refused before generation.</Empty>
        ) : (
          <div className="space-y-2">
            {report.stages.map((t) => (
              <StageBar key={t.stage} timing={t} max={report.total_duration_ms} />
            ))}
          </div>
        )}
      </Section>

      {/* §10 citations */}
      <Section n={10} title="Source Citations">
        <CitationList
          citations={report.citations.map((c) => ({
            claim_ordinal: c.claim_ordinal,
            source_name: c.source_name,
            page: c.page,
          }))}
        />
      </Section>

      {/* contribution (rag-design §6b) */}
      {report.contribution ? (
        <Card>
          <CardHeader>
            <CardTitle>Repository Contribution</CardTitle>
          </CardHeader>
          <CardBody>
            <ContributionPanel contribution={report.contribution} />
          </CardBody>
        </Card>
      ) : null}
    </div>
  );
}

function Section({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader className="flex items-center gap-2">
        <span className="grid h-5 w-5 place-items-center rounded bg-surface-2 font-mono text-[11px] text-muted">
          {n}
        </span>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardBody>{children}</CardBody>
    </Card>
  );
}

function RetrievalSection({
  n,
  title,
  items,
}: {
  n: number;
  title: string;
  items: RetrievalItemType[];
}) {
  return (
    <Section n={n} title={title}>
      {items.length === 0 ? (
        <Empty>None retrieved.</Empty>
      ) : (
        <div className="space-y-2">
          {items.map((item) => (
            <RetrievalItem key={item.chunk_id} item={item} />
          ))}
        </div>
      )}
    </Section>
  );
}

function QualityRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between border-b border-border/50 pb-2 text-sm">
      <span className="text-muted">{label}</span>
      <span className="font-mono text-ink">{value}</span>
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="text-sm text-muted">{children}</p>;
}
