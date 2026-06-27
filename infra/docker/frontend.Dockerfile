# Frontend image — Next.js (standalone) thin UI.
#
# Build from the frontend/ directory as context:
#   docker build -f infra/docker/frontend.Dockerfile -t fpp/frontend:0.1.0 frontend
#
# The browser never reaches the backend directly; the Next server's route handlers
# proxy to BACKEND_URL (set at runtime). `output: "standalone"` keeps the runtime
# image to the traced server bundle only. Runs as a non-root user.

# --- deps --------------------------------------------------------------------
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# --- builder -----------------------------------------------------------------
FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# --- runtime -----------------------------------------------------------------
FROM node:20-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN addgroup -S app && adduser -S app -G app

COPY --from=builder /app/public ./public
COPY --from=builder --chown=app:app /app/.next/standalone ./
COPY --from=builder --chown=app:app /app/.next/static ./.next/static

USER app
EXPOSE 3000

CMD ["node", "server.js"]
