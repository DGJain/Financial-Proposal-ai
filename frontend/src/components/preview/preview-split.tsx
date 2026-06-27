"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { ApiError, exportEditedProposal, getProposalDocument } from "@/lib/api-client/client";
import type { ExportFormat } from "@/types/api";

/**
 * WYSIWYG proposal editor. Loads the server-rendered company-template document
 * (`GET .../document`) into a same-origin `srcDoc` iframe — the iframe isolates the
 * document's print CSS from the app shell and `designMode` makes the page directly
 * editable. Export posts the *edited* HTML back (`POST .../export`), so the PDF/DOCX
 * is exactly what's on screen.
 */
export function PreviewSplit({ proposalId }: { proposalId: string }) {
  const [docHtml, setDocHtml] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState<ExportFormat | null>(null);
  const frameRef = useRef<HTMLIFrameElement>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    getProposalDocument(proposalId)
      .then((html) => {
        if (alive) setDocHtml(html);
      })
      .catch((err) => {
        if (alive) setError(err instanceof ApiError ? err.message : "Failed to load document.");
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [proposalId]);

  const syncHeight = useCallback(() => {
    const frame = frameRef.current;
    const body = frame?.contentDocument?.body;
    if (frame && body) frame.style.height = `${body.scrollHeight + 48}px`;
  }, []);

  // On iframe load: enable editing and size to content; keep height in sync as edited.
  function onFrameLoad() {
    const doc = frameRef.current?.contentDocument;
    if (!doc) return;
    doc.designMode = "on";
    doc.addEventListener("input", syncHeight);
    syncHeight();
  }

  function currentHtml(): string {
    const doc = frameRef.current?.contentDocument;
    const node = doc?.querySelector(".doc");
    return node?.outerHTML ?? docHtml ?? "";
  }

  async function onExport(format: ExportFormat) {
    setExporting(format);
    setError(null);
    try {
      const blob = await exportEditedProposal(proposalId, currentHtml(), format);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${proposalId}.${format}`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Export failed.");
    } finally {
      setExporting(null);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-muted">
        <Spinner /> Loading document…
      </div>
    );
  }
  if (docHtml === null) {
    return (
      <p className="rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
        {error ?? "Proposal not found."}
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="rounded-lg border border-border bg-surface-2 px-4 py-2 text-xs text-muted">
          Edit the document directly — click anywhere and type. Export converts exactly
          what you see into PDF or DOCX.
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            onClick={() => onExport("docx")}
            disabled={exporting !== null}
          >
            {exporting === "docx" ? <Spinner /> : "⬇"} Export DOCX
          </Button>
          <Button onClick={() => onExport("pdf")} disabled={exporting !== null}>
            {exporting === "pdf" ? <Spinner /> : "⬇"} Export PDF
          </Button>
        </div>
      </div>

      {error ? (
        <p className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">
          {error}
        </p>
      ) : null}

      <div className="overflow-hidden rounded-xl border border-border bg-white shadow-sm">
        <iframe
          ref={frameRef}
          title="Proposal document"
          srcDoc={docHtml}
          onLoad={onFrameLoad}
          className="w-full"
          style={{ minHeight: "60vh", border: "0" }}
        />
      </div>
    </div>
  );
}
