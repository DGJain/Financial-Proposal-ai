import type { NextRequest } from "next/server";

import { proxyUpload } from "@/server/backend";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest): Promise<Response> {
  return proxyUpload(req, "/ingest/financial");
}
