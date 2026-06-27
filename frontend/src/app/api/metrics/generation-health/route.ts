import type { NextRequest } from "next/server";

import { proxyJson } from "@/server/backend";

export const dynamic = "force-dynamic";

export async function GET(req: NextRequest): Promise<Response> {
  // Forward ?days to the backend's generation-health endpoint.
  return proxyJson(req, `/metrics/generation-health${req.nextUrl.search}`, "GET");
}
