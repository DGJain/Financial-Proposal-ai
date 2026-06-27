import type { NextRequest } from "next/server";

import { proxyJson } from "@/server/backend";

export const dynamic = "force-dynamic";

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ proposalId: string }> },
): Promise<Response> {
  const { proposalId } = await params;
  return proxyJson(req, `/proposals/${encodeURIComponent(proposalId)}/versions`, "POST");
}
