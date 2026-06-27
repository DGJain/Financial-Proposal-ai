/**
 * Browser API client — calls the same-origin Next.js route handlers (`/api/**`),
 * which proxy to the internal backend. The caller's ACL/engagement context is sent
 * as `X-*` headers so the backend can enforce the deal-team wall on retrieval.
 */

import type {
  AttachmentExtraction,
  EditRequest,
  ExecutionReport,
  ExportFormat,
  GenerateRequest,
  GenerateResponse,
  GenerationHealth,
  Health,
  IngestResponse,
  PromptHistory,
  Proposal,
  RepositoryMetrics,
  RequesterContext,
} from "@/types/api";

function aclHeaders(ctx?: RequesterContext): Record<string, string> {
  const headers: Record<string, string> = {};
  if (ctx?.engagementId) headers["X-Engagement-Id"] = ctx.engagementId;
  if (ctx?.aclGroups) headers["X-ACL-Groups"] = ctx.aclGroups;
  if (ctx?.classification) headers["X-Classification"] = ctx.classification;
  if (ctx?.requestedBy) headers["X-Requested-By"] = ctx.requestedBy;
  return headers;
}

async function asJson<T>(res: Response): Promise<T> {
  const text = await res.text();
  const data = text ? JSON.parse(text) : {};
  if (!res.ok) {
    const detail =
      typeof data?.detail === "string" ? data.detail : `Request failed (${res.status})`;
    throw new ApiError(detail, res.status);
  }
  return data as T;
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export async function generateProposal(
  body: GenerateRequest,
  ctx: RequesterContext,
): Promise<GenerateResponse> {
  const res = await fetch("/api/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...aclHeaders(ctx) },
    body: JSON.stringify(body),
  });
  return asJson<GenerateResponse>(res);
}

export async function getProposal(proposalId: string): Promise<Proposal> {
  const res = await fetch(`/api/proposals/${encodeURIComponent(proposalId)}`, {
    cache: "no-store",
  });
  return asJson<Proposal>(res);
}

export async function editProposal(
  proposalId: string,
  body: EditRequest,
  ctx: RequesterContext,
): Promise<Proposal> {
  const res = await fetch(`/api/proposals/${encodeURIComponent(proposalId)}/versions`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...aclHeaders(ctx) },
    body: JSON.stringify(body),
  });
  return asJson<Proposal>(res);
}

// --- Phase 5: analytics / reporting reads ------------------------------------
// These are audit/lineage reads, not ACL-filtered retrieval, so they carry no
// X-* deal-team headers.

export async function getExecutionReport(genId: string): Promise<ExecutionReport> {
  const res = await fetch(`/api/report/${encodeURIComponent(genId)}`, { cache: "no-store" });
  return asJson<ExecutionReport>(res);
}

export async function getHistory(limit = 50, offset = 0): Promise<PromptHistory> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  const res = await fetch(`/api/history?${params.toString()}`, { cache: "no-store" });
  return asJson<PromptHistory>(res);
}

export async function getHealth(): Promise<Health> {
  const res = await fetch("/api/health", { cache: "no-store" });
  return asJson<Health>(res);
}

export async function getRepositoryMetrics(): Promise<RepositoryMetrics> {
  const res = await fetch("/api/metrics/repository", { cache: "no-store" });
  return asJson<RepositoryMetrics>(res);
}

export async function getGenerationHealth(days = 7): Promise<GenerationHealth> {
  const res = await fetch(`/api/metrics/generation-health?days=${days}`, { cache: "no-store" });
  return asJson<GenerationHealth>(res);
}

/** Same-origin URL for the rendered export (open in a new tab to view/save). */
export function exportProposalUrl(proposalId: string, format: ExportFormat): string {
  return `/api/proposals/${encodeURIComponent(proposalId)}/export?format=${format}`;
}

/** Fetch the styled, editable HTML document for the WYSIWYG preview. */
export async function getProposalDocument(proposalId: string): Promise<string> {
  const res = await fetch(`/api/proposals/${encodeURIComponent(proposalId)}/document`, {
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text();
    throw new ApiError(text || `Failed to load document (${res.status})`, res.status);
  }
  return res.text();
}

/** Convert the editor's current HTML to PDF/DOCX server-side and return the file. */
export async function exportEditedProposal(
  proposalId: string,
  html: string,
  format: ExportFormat,
): Promise<Blob> {
  const res = await fetch(
    `/api/proposals/${encodeURIComponent(proposalId)}/export?format=${format}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ html }),
    },
  );
  if (!res.ok) {
    let detail = `Export failed (${res.status})`;
    try {
      const data = JSON.parse(await res.text());
      if (typeof data?.detail === "string") detail = data.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(detail, res.status);
  }
  return res.blob();
}

/**
 * Extract text from an uploaded binary (PDF/DOCX/PPTX/image) server-side so it can
 * be attached as query context. Browsers can't parse these formats and the backend
 * is air-gapped, so extraction runs there. A format whose library/binary is
 * unavailable returns `extracted: false` with a reason (then attach by name only).
 */
export async function extractAttachment(
  file: File,
  fileType: string,
): Promise<AttachmentExtraction> {
  const params = new URLSearchParams({ filename: file.name, file_type: fileType });
  const res = await fetch(`/api/generate/extract?${params.toString()}`, {
    method: "POST",
    headers: { "Content-Type": "application/octet-stream" },
    body: await file.arrayBuffer(),
  });
  return asJson<AttachmentExtraction>(res);
}

export async function ingestFinancial(
  file: File,
  fileType: string,
  ctx: RequesterContext,
): Promise<IngestResponse> {
  const params = new URLSearchParams({ filename: file.name, file_type: fileType });
  const res = await fetch(`/api/ingest/financial?${params.toString()}`, {
    method: "POST",
    headers: { "Content-Type": "application/octet-stream", ...aclHeaders(ctx) },
    body: await file.arrayBuffer(),
  });
  return asJson<IngestResponse>(res);
}
