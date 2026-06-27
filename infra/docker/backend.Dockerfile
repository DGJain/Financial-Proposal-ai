# Backend image — FastAPI/uvicorn service.
#
# Build from the backend/ directory as context:
#   docker build -f infra/docker/backend.Dockerfile -t fpp/backend:0.1.0 backend
#
# Multi-stage: a builder resolves dependencies into an isolated virtualenv; the
# runtime stage copies only that venv + the app and runs as a non-root user with a
# read-only-friendly layout. Internal-only image — no secrets are baked in; all
# configuration arrives via env (ConfigMap/Secret) at runtime.

# --- builder -----------------------------------------------------------------
FROM python:3.11-slim AS builder

ENV POETRY_VERSION=1.8.5 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false

RUN pip install "poetry==${POETRY_VERSION}" poetry-plugin-export

WORKDIR /build
# Lockfile is generated here when absent so the resolution is captured in-layer.
COPY pyproject.toml poetry.lock* ./
RUN poetry lock --no-update 2>/dev/null || poetry lock
RUN poetry export --only main --without-hashes -f requirements.txt -o requirements.txt

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"
RUN pip install --no-cache-dir -r requirements.txt

# --- runtime -----------------------------------------------------------------
FROM python:3.11-slim AS runtime

# Native libs required by PyMuPDF / PaddleOCR (image + GL stack), no recommends.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY . .

# Drop to an unprivileged user; the container can run with a read-only rootfs.
RUN addgroup --system app && adduser --system --ingroup app --home /app app \
    && chown -R app:app /app
USER app

EXPOSE 8000

# Liveness mirrors the K8s probe so `docker run` is self-checking too.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
