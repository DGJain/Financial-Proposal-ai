import type { NextRequest } from "next/server";

import { proxyJson } from "@/server/backend";

export const dynamic = "force-dynamic";

export async function GET(req: NextRequest): Promise<Response> {
  // Forward ?limit & ?offset to the backend's history endpoint.
  return proxyJson(req, `/history${req.nextUrl.search}`, "GET");
}
