# Financial Proposal Platform — Frontend

Thin UI (Next.js 15 App Router · TypeScript · Tailwind) for the air-gapped
proposal platform: **upload evidence · generate · preview/edit**. History,
metrics, and the Execution Report are Phase 5.

## Architecture

The browser never calls the internal API directly. Same-origin route handlers
under `src/app/api/**` run on the Next.js server and proxy to the backend
(`BACKEND_URL`), forwarding only the caller's ACL/engagement `X-*` headers. This
keeps the internal API host server-side and avoids cross-origin exposure of the
deal-team walls.

```
src/
├── app/
│   ├── (workspace)/{generate,upload,preview/[proposalId]}/  # pages
│   └── api/{generate,ingest,proposals}/                     # server-side proxies
├── components/{generation,preview,upload,layout,ui}/        # view + primitives
├── lib/{api-client,hooks,utils}/                            # browser client
├── server/backend.ts                                        # proxy helper
└── types/api.ts                                             # wire types (mirror backend DTOs)
```

## Run

```bash
npm install
BACKEND_URL=http://localhost:8000 npm run dev   # http://localhost:3000
```

The ACL/engagement context defaults to the seeded local backend
(`engagement=eng-1`, `groups=consultants`) so a brief grounds out of the box.
Switching the engagement demonstrates the deal-team wall (evidence becomes
invisible → a refusal).

## Verify

```bash
npm run build       # production build: typechecks + lints
npm run typecheck   # tsc --noEmit only
npm run lint        # eslint only
```
