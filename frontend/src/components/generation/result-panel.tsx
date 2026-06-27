import Link from "next/link";

import { Badge, type Tone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { CitationList } from "@/components/generation/citation-list";
import { ConfidenceBadge } from "@/components/generation/confidence-badge";
import { ContributionPanel } from "@/components/generation/contribution-panel";
import type { GenerateResponse, GenerationOutcome } from "@/types/api";

const OUTCOME: Record<GenerationOutcome, { tone: Tone; label: string }> = {
  generated: { tone: "success", label: "✓ Generated" },
  style_only: { tone: "warn", label: "◐ Style-only" },
  draft: { tone: "warn", label: "◐ Draft" },
  refused: { tone: "danger", label: "✕ Refused" },
};

export function ResultPanel({ result }: { result: GenerateResponse }) {
  const outcome = OUTCOME[result.outcome];
  return (
    <Card>
      <CardHeader className="flex items-center justify-between">
        <CardTitle>Generation result</CardTitle>
        <div className="flex items-center gap-2">
          <Badge tone={outcome.tone}>{outcome.label}</Badge>
          <ConfidenceBadge band={result.confidence.band} score={result.confidence.score} />
        </div>
      </CardHeader>
      <CardBody className="space-y-6">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-1 text-xs text-muted">
          <span>
            Report&nbsp;
            <span className="font-mono text-ink">{result.report_id}</span>
          </span>
          {result.proposal ? (
            <span>
              Proposal&nbsp;
              <span className="font-mono text-ink">{result.proposal.proposal_id}</span>
            </span>
          ) : null}
        </div>

        {result.outcome === "refused" ? (
          <div className="rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-ink">
            <p className="mb-1 font-medium text-danger">Refused — no grounded answer.</p>
            <p className="text-muted">{result.refusal_reason}</p>
          </div>
        ) : null}

        {result.outcome === "style_only" ? (
          <div className="rounded-lg border border-warn/30 bg-warn/10 px-4 py-3 text-sm text-ink">
            <p className="mb-1 font-medium text-warn">Style-only draft — no financial evidence.</p>
            <p className="text-muted">
              No evidence in the knowledge base matched this company, so this draft
              follows the company template and the style of past winning proposals but
              states <span className="font-medium text-ink">no financial figures</span>.
              Attach the relevant financials to ground specific numbers.
            </p>
          </div>
        ) : null}

        {result.contribution ? (
          <ContributionPanel contribution={result.contribution} />
        ) : null}

        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">
            Citations (financial evidence)
          </p>
          <CitationList citations={result.citations} />
        </div>

        {result.proposal ? (
          <div className="flex justify-end">
            <Link href={`/preview/${result.proposal.proposal_id}`}>
              <Button>Open preview &amp; edit →</Button>
            </Link>
          </div>
        ) : null}
      </CardBody>
    </Card>
  );
}
