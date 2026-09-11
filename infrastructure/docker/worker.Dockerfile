# ─────────────────────────────────────────────
# AIDSE Worker — Dockerfile (multi-stage)
# Section 12.1 — services/worker
# ─────────────────────────────────────────────

FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim AS runtime

RUN groupadd --gid 1001 aidse \
    && useradd --uid 1001 --gid aidse --shell /bin/bash --create-home aidse

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

COPY services/worker ./services/worker
COPY packages ./packages
COPY pyproject.toml .

RUN chown -R aidse:aidse /app

USER aidse

CMD ["celery", "-A", "services.worker.celery_app", "worker", "--loglevel=info", "--concurrency=4"]
