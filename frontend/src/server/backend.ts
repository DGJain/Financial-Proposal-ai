/**
 * Server-side bridge to the internal FastAPI backend.
 *
 * The browser never calls the backend directly (air-gapped, internal-only). The
 * route handlers under `app/api/**` run on the Next.js server and forward to
 * `BACKEND_URL`, carrying only the caller's ACL/engagement `X-*` headers through.
 * This keeps the internal API host server-side and avoids any cross-origin
 * exposure of the deal-team walls.
 */

import type { NextRequest } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

const FORWARD_HEADERS = [
  "x-acl-groups",
  "x-engagement-id",
  "x-classification",
  "x-requested-by",
  "x-known-identifiers",
];

function forwardedHeaders(req: NextRequest): Headers {
  const out = new Headers();
  for (const name of FORWARD_HEADERS) {
    const value = req.headers.get(name);
    if (value) out.set(name, value);
  }
  return out;
}

async function relay(res: Response): Promise<Response> {
  const text = await res.text();
  return new Response(text, {
    status: res.status,
    headers: { "content-type": res.headers.get("content-type") ?? "application/json" },
  });
}

/** Fetch the backend, turning an unreachable host into a clean 502 JSON error
 * instead of an unhandled route-handler exception. */
async function safeFetch(url: string, init: RequestInit): Promise<Response> {
  try {
    return await relay(await fetch(url, init));
  } catch {
    return Response.json(
      { detail: "Backend unavailable. Is the API server running?" },
      { status: 502 },
    );
  }
}

/** Proxy a JSON request/response (generate, proposal read, edit). */
export async function proxyJson(
  req: NextRequest,
  path: string,
  method: "GET" | "POST" = "POST",
): Promise<Response> {
  const headers = forwardedHeaders(req);
  let body: string | undefined;
  if (method !== "GET") {
    body = await req.text();
    headers.set("content-type", "application/json");
  }
  return safeFetch(`${BACKEND_URL}${path}`, { method, headers, body, cache: "no-store" });
}

/** Proxy a binary GET download (PDF/DOCX export), preserving bytes + headers.
 * The JSON `relay` above decodes the body as text, which corrupts binary files —
 * this passes the raw bytes through and keeps content-type + content-disposition. */
export async function proxyBinary(req: NextRequest, path: string): Promise<Response> {
  const headers = forwardedHeaders(req);
  try {
    const upstream = await fetch(`${BACKEND_URL}${path}`, {
      method: "GET",
      headers,
      cache: "no-store",
    });
    const body = await upstream.arrayBuffer();
    const out = new Headers();
    const contentType = upstream.headers.get("content-type");
    const disposition = upstream.headers.get("content-disposition");
    if (contentType) out.set("content-type", contentType);
    if (disposition) out.set("content-disposition", disposition);
    return new Response(body, { status: upstream.status, headers: out });
  } catch {
    return Response.json(
      { detail: "Backend unavailable. Is the API server running?" },
      { status: 502 },
    );
  }
}

/** Proxy a JSON POST whose *response* is a binary download (edited-HTML export).
 * Sends the JSON body through and passes the returned bytes + headers back intact. */
export async function proxyBinaryPost(req: NextRequest, path: string): Promise<Response> {
  const headers = forwardedHeaders(req);
  headers.set("content-type", "application/json");
  const body = await req.text();
  try {
    const upstream = await fetch(`${BACKEND_URL}${path}`, {
      method: "POST",
      headers,
      body,
      cache: "no-store",
    });
    const bytes = await upstream.arrayBuffer();
    const out = new Headers();
    const contentType = upstream.headers.get("content-type");
    const disposition = upstream.headers.get("content-disposition");
    if (contentType) out.set("content-type", contentType);
    if (disposition) out.set("content-disposition", disposition);
    return new Response(bytes, { status: upstream.status, headers: out });
  } catch {
    return Response.json(
      { detail: "Backend unavailable. Is the API server running?" },
      { status: 502 },
    );
  }
}

/** Proxy a raw binary upload (financial ingest), forwarding query + body bytes. */
export async function proxyUpload(req: NextRequest, basePath: string): Promise<Response> {
  const search = req.nextUrl.search; // ?filename=...&file_type=...
  const headers = forwardedHeaders(req);
  headers.set("content-type", req.headers.get("content-type") ?? "application/octet-stream");
  const body = await req.arrayBuffer();
  return safeFetch(`${BACKEND_URL}${basePath}${search}`, {
    method: "POST",
    headers,
    body,
    cache: "no-store",
  });
}
