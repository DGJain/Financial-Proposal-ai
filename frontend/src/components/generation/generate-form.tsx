"use client";

import { useEffect, useRef, useState } from "react";

import { ResultPanel } from "@/components/generation/result-panel";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { Textarea } from "@/components/ui/field";
import { Spinner } from "@/components/ui/spinner";
import {
  ApiError,
  extractAttachment,
  generateProposal,
  getHealth,
} from "@/lib/api-client/client";
import { useRequester } from "@/lib/hooks/use-requester";
import type { Attachment, GenerateRequest, GenerateResponse } from "@/types/api";

// The composer is query-first: the backend infers company / period / sector /
// figures from the query, so the brief fields are sent with these defaults
// (blank = auto-detected). proposal_type matches the seeded template/exemplar.
const BRIEF_DEFAULTS = {
  proposal_type: "statement_of_work",
};

// Text-family files are read client-side and fed to the model as query context.
const TEXT_EXT = /\.(txt|md|markdown|csv|tsv|json|log|text)$/i;
// Binary docs the user can attach. PDF/DOCX/PPTX/image extensions are extracted
// server-side (browsers can't parse them); the rest ride along by name only.
const BINARY_EXT = /\.(pdf|png|jpe?g|gif|webp|bmp|tiff?|doc|docx|ppt|pptx|xls|xlsx)$/i;
// Extension → backend FileType for the server-side text extractor.
const EXTRACTABLE: Record<string, string> = {
  pdf: "pdf",
  docx: "docx",
  pptx: "pptx",
  png: "png",
  jpg: "jpg",
  jpeg: "jpg",
};
const ATTACH_ACCEPT = [
  ".txt,.md,.markdown,.csv,.tsv,.json,.log,.text",
  ".pdf,.png,.jpg,.jpeg,.gif,.webp,.bmp,.tif,.tiff",
  ".doc,.docx,.ppt,.pptx,.xls,.xlsx",
  "text/*,application/pdf,image/*",
].join(",");

export function GenerateForm() {
  const { requester } = useRequester();
  const [query, setQuery] = useState("");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [result, setResult] = useState<GenerateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [model, setModel] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  // Show which model actually generates (the local SLM), read live from the backend.
  useEffect(() => {
    getHealth()
      .then((h) => setModel(h.llm_model_id))
      .catch(() => setModel(null));
  }, []);

  // "ollama:qwen2.5:3b" → "qwen2.5:3b" for display; keep the full id in the tooltip.
  const modelLabel = model ? model.replace(/^[a-z0-9_-]+:/i, "") : null;

  async function onAttach(files: FileList | null) {
    if (!files) return;
    setError(null);
    const next: Attachment[] = [];
    const notes: string[] = [];
    setExtracting(true);
    try {
      for (const file of Array.from(files)) {
        if (TEXT_EXT.test(file.name) || file.type.startsWith("text/")) {
          next.push({ name: file.name, text: await file.text() });
          continue;
        }
        const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
        const fileType = EXTRACTABLE[ext];
        if (fileType) {
          // PDF/DOCX/PPTX/image → extract text server-side, fall back to name-only.
          try {
            const res = await extractAttachment(file, fileType);
            if (res.extracted && res.text.trim()) {
              next.push({ name: file.name, text: res.text });
            } else {
              next.push({ name: file.name, text: "" });
              notes.push(`${file.name}: ${res.detail || "no text found"}`);
            }
          } catch {
            next.push({ name: file.name, text: "" });
            notes.push(`${file.name}: extraction failed — attached by name`);
          }
        } else if (BINARY_EXT.test(file.name) || file.type.startsWith("image/")) {
          // Recognised binary the extractor doesn't handle (e.g. .doc/.xls) → name only.
          next.push({ name: file.name, text: "" });
        } else {
          notes.push(`Unsupported, skipped: ${file.name}`);
        }
      }
    } finally {
      setExtracting(false);
    }
    if (next.length) setAttachments((prev) => [...prev, ...next]);
    if (notes.length) setError(notes.join(" · "));
    if (fileInput.current) fileInput.current.value = "";
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!query.trim()) {
      setError("Describe the proposal you need.");
      return;
    }
    setPending(true);
    setError(null);
    setResult(null);
    try {
      // Query-first: the backend auto-detects entity / year / sector / figures from
      // the query, so the brief is sent blank apart from a derived title and type.
      const payload: GenerateRequest = {
        title: query.trim().slice(0, 80),
        proposal_type: BRIEF_DEFAULTS.proposal_type,
        entity: null,
        fiscal_year: null,
        sector: null,
        line_items: [],
        instructions: "",
        query: query.trim(),
        attachments,
      };
      setResult(await generateProposal(payload, requester));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Generation failed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* Composer */}
      <Card className="overflow-hidden">
        <CardBody className="space-y-3">
          <form onSubmit={onSubmit} className="space-y-3">
            <Textarea
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="What proposal do you need? Just name the company — e.g. “Draft a statement of work for an FY2024 audit of Acme Corp, emphasising our methodology and independence.” The company, year and sector are detected from your text."
              className="min-h-28 resize-y border-0 bg-transparent px-1 text-base focus:ring-0"
            />

            {attachments.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {attachments.map((a, i) => (
                  <span
                    key={`${a.name}-${i}`}
                    className="inline-flex items-center gap-2 rounded-full border border-border bg-surface-2 px-3 py-1 text-xs text-ink"
                  >
                    📎 {a.name}
                    {a.text.trim() ? null : (
                      <span className="text-[10px] text-muted">name only</span>
                    )}
                    <button
                      type="button"
                      onClick={() => setAttachments((p) => p.filter((_, j) => j !== i))}
                      className="text-muted hover:text-danger"
                      aria-label={`Remove ${a.name}`}
                    >
                      ✕
                    </button>
                  </span>
                ))}
                <span className="w-full text-[11px] text-muted">
                  Text and PDF/DOCX/PPTX content is read in as context; images and other
                  files attach by name only. Attached text guides the prose — it is not
                  citable evidence.
                </span>
              </div>
            ) : null}

            {extracting ? (
              <p className="text-[11px] text-muted">Reading attachments…</p>
            ) : null}

            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => fileInput.current?.click()}
                  className="grid h-9 w-9 place-items-center rounded-full border border-border text-lg text-muted transition-colors hover:bg-surface-2 hover:text-ink"
                  title="Attach files (docs, PDF, images, text)"
                  aria-label="Attach files"
                >
                  +
                </button>
                <input
                  ref={fileInput}
                  type="file"
                  multiple
                  accept={ATTACH_ACCEPT}
                  className="hidden"
                  onChange={(e) => onAttach(e.target.files)}
                />
              </div>
              <div className="flex items-center gap-3">
                {modelLabel ? (
                  <span
                    className="inline-flex items-center gap-1.5 text-xs text-muted"
                    title={`Generation model — ${model} (local, air-gapped)`}
                  >
                    <span className="h-1.5 w-1.5 rounded-full bg-success" />
                    {modelLabel}
                    <span className="text-[10px] uppercase tracking-wide text-muted/70">
                      local
                    </span>
                  </span>
                ) : null}
                <Button type="submit" disabled={pending || extracting}>
                  {pending ? <Spinner /> : "✦"} Generate
                </Button>
              </div>
            </div>

            {error ? (
              <p className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">
                {error}
              </p>
            ) : null}
          </form>
        </CardBody>
      </Card>

      {result ? <ResultPanel result={result} /> : null}
    </div>
  );
}
