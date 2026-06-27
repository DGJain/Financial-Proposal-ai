/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Emit a self-contained server bundle (`.next/standalone`) so the production
  // container ships only the traced runtime, not a full node_modules tree.
  output: "standalone",
  // The browser never calls the internal API directly; same-origin route handlers
  // under /app/api proxy to the backend (air-gapped, internal-only).
  env: {
    BACKEND_URL: process.env.BACKEND_URL ?? "http://localhost:8000",
  },
};

export default nextConfig;
