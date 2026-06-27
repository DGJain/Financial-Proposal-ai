import type { NextRequest } from "next/server";

import { proxyBinary, proxyBinaryPost } from "@/server/backend";

export const dynamic = "force-dynamic";

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ proposalId: string }> },
): Promise<Response> {
  const { proposalId } = await params;
  // Forward ?format=markdown|html|pdf|docx; binary-safe so PDF/DOCX bytes survive.
  return proxyBinary(
    req,
    `/proposals/${encodeURIComponent(proposalId)}/export${req.nextUrl.search}`,
  );
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ proposalId: string }> },
): Promise<Response> {
  const { proposalId } = await params;
  // Body { html } from the WYSIWYG editor; response is the converted PDF/DOCX bytes.
  return proxyBinaryPost(
    req,
    `/proposals/${encodeURIComponent(proposalId)}/export${req.nextUrl.search}`,
  );
}
