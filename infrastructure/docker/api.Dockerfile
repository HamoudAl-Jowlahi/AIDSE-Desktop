# ─────────────────────────────────────────────
# AIDSE API — Dockerfile (multi-stage)
# Section 12.1 — apps/api
# ─────────────────────────────────────────────

# Stage 1: Build dependencies
FROM python:3.11-slim AS builder

WORKDIR /build

# Install system deps for psycopg2/asyncpg build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Runtime (non-root)
FROM python:3.11-slim AS runtime

# Security: non-root user (Section 13)
RUN groupadd --gid 1001 aidse \
    && useradd --uid 1001 --gid aidse --shell /bin/bash --create-home aidse

WORKDIR /app

# Install system runtime deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy source (only what's needed for the API)
COPY apps/api ./apps/api
COPY packages ./packages
COPY pyproject.toml .

RUN chown -R aidse:aidse /app

USER aidse

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
