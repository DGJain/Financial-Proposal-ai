import type { NextRequest } from "next/server";

import { proxyJson } from "@/server/backend";

export const dynamic = "force-dynamic";

export async function GET(req: NextRequest): Promise<Response> {
  return proxyJson(req, "/health", "GET");
}
