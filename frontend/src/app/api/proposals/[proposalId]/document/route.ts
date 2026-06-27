import type { NextRequest } from "next/server";

import { proxyBinary } from "@/server/backend";

export const dynamic = "force-dynamic";

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ proposalId: string }> },
): Promise<Response> {
  const { proposalId } = await params;
  // Styled, editable HTML document for the WYSIWYG preview (content-type preserved).
  return proxyBinary(req, `/proposals/${encodeURIComponent(proposalId)}/document`);
}
