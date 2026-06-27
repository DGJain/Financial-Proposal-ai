import type { NextRequest } from "next/server";

import { proxyJson } from "@/server/backend";

export const dynamic = "force-dynamic";

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
): Promise<Response> {
  const { id } = await params;
  return proxyJson(req, `/report/${encodeURIComponent(id)}`, "GET");
}
