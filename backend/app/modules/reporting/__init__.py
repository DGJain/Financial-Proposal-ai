"""Read-side reporting use-cases (Phase 5).

Pure read/aggregate use-cases over the existing append-only lineage: the
Execution Report (`/report/{gen_id}`) and Prompt-History analytics (`/history`).
They compute nothing the pipeline did not already record — they reconstruct and
join it. The per-document quality (OCR / EQS / information-loss) lives in the
ingestion lineage, so each run's *financial* retrieval hits are joined back to
their source documents' quality and aggregated (document-intelligence.md U-4).
"""
