# Deployment & Operations (Phase 6)

Air-gapped, internal-only deployment of the Financial Proposal Platform:
container images, Kubernetes manifests, network-level air-gap enforcement, and
verification tooling.

## Layout

```
infra/
  docker/                 backend.Dockerfile · frontend.Dockerfile (non-root, multi-stage)
  k8s/
    namespaces/           fpp-app · fpp-data · fpp-ai (restricted Pod Security)
    app/                  backend · frontend · ConfigMap · Secret · migration Job · ingress
    data/                 PostgreSQL · Redis · ChromaDB · MinIO StatefulSets
    ai/                   embedding + SLM serving (GPU)
    policies/             default-deny + allow-dns + allowed-flows NetworkPolicies
    kustomization.yaml    aggregates everything; pins image tags
  scripts/
    migrate/              alembic upgrade head
    seed/                 demo data into a real DB
    snapshots/            ChromaDB snapshot/restore
    e2e/                  live end-to-end (real PostgreSQL)
    validate_manifests.py offline structural + hardening lint
  observability/          (reserved)
```

## Build images

```sh
docker build -f infra/docker/backend.Dockerfile  -t fpp/backend:0.1.0  backend
docker build -f infra/docker/frontend.Dockerfile -t fpp/frontend:0.1.0 frontend
```

Both run as non-root. The backend exposes `/health` (liveness) and `/ready`
(readiness — round-trips PostgreSQL + ChromaDB). The frontend is a Next.js
`standalone` server whose route handlers proxy to `BACKEND_URL`; the browser never
reaches the API directly.

## Deploy

```sh
kubectl apply -k infra/k8s            # namespaces, app, data, ai, network policies
kubectl -n fpp-app create job db-migrate-1 --from=job/db-migrate   # or apply the Job
```

Replace the placeholder `Secret`s (`CHANGEME`) via Sealed Secrets / External
Secrets before applying to a real cluster.

### The air-gap, in the cluster

`policies/default-deny.yaml` denies all ingress **and egress** in every namespace.
The only egress allowed is cluster DNS (`allow-dns.yaml`) plus the explicit
intra-cluster flows in `allow-flows.yaml`:

```
ingress ──► frontend:3000 ──► backend:8000 ──► data (5432/6379/8000/9000) + ai (8080)
```

No policy permits internet egress — the air-gap is enforced at the network layer,
matching the fail-closed `air_gapped` setting in the app.

## Verify

Offline manifest lint (no cluster needed):

```sh
kubectl kustomize infra/k8s | python infra/scripts/validate_manifests.py -
```

Live end-to-end against a real PostgreSQL (validates migrations + real DB
round-trips + the running ASGI app + the Phase 5 read surface — the integration
the unit tests fake with SQLite):

```sh
PYTHON=backend/.venv/Scripts/python.exe sh infra/scripts/e2e/run_local_e2e.sh
```

## Local development

### Real prose without a key (offline, air-gap-safe)

In production the generator is the internal SLM (`ai/` namespace). For **local
demos** the LLM gateway selects, in order (`make_llm_gateway`, `ENVIRONMENT=local`
only):

1. **Local open-source model via Ollama** — `AI_DEV_USE_LOCAL=1`. Talks to a local
   Ollama daemon on `localhost:11434` with **no API key and no external egress**, so
   the air-gap is preserved. This is the realistic stand-in for the production SLM.
2. **Claude** — `AI_DEV_USE_CLAUDE=1` + `AI_CLAUDE_API_KEY=…`. Prototype only; makes
   an outbound call, so it is **not** air-gapped. `dev_use_local` takes precedence.
3. Otherwise the deterministic `EchoGateway` placeholder.

Retrieval, grounding, citations and contribution metrics are always real — the
gateway only writes the prose.

```sh
# one-time: install Ollama (https://ollama.com), then pull the model
ollama serve &                 # daemon on localhost:11434
ollama pull qwen2.5:3b         # ~1.9 GB; default local_model

# launch the backend against it
AI_DEV_USE_LOCAL=1 AI_LOCAL_MODEL=qwen2.5:3b \
  backend/.venv/Scripts/python.exe infra/scripts/dev/serve_with_seed.py
```

Settings (`AISettings`, env prefix `AI_`): `dev_use_local`, `local_endpoint`
(default `http://localhost:11434`), `local_model` (default `qwen2.5:3b`). The
`OllamaGateway` sets `num_ctx=8192` explicitly — Ollama otherwise defaults to 2048
and would silently truncate the assembled grounded context. On a CPU-only host a
generation takes tens of seconds to a few minutes; pick a smaller model
(`qwen2.5:1.5b`, `llama3.2:1b`) for speed or a larger one (`qwen2.5:7b`) on a GPU.

### Export rendering dependency

Proposal export converts the editor's HTML to PDF via **`xhtml2pdf`** (pure-Python,
pulls `reportlab`) and to DOCX via `python-docx` — both in `pyproject.toml`, no
system libraries or network needed.
