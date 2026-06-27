import type { NextRequest } from "next/server";

import { proxyUpload } from "@/server/backend";

export const dynamic = "force-dynamic";

/** Forward an uploaded binary (query + body bytes) to the backend text extractor. */
export async function POST(req: NextRequest): Promise<Response> {
  return proxyUpload(req, "/generate/extract");
}
