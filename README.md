# AIDSE Platform

**AI Data Scientist & AI Evaluation Platform** — Unified SaaS for model training, evaluation, regression detection, explainability, and MLOps monitoring.

> Phase 0 (Foundation) — Authentication + Project management + Infrastructure skeleton

---

## Quick Start (Local Development)

### Prerequisites
- Docker Desktop (running)
- Python 3.11+
- Node.js 20+
- Git

### 1. Clone and setup environment
```bash
git clone <repo-url>
cd aidse-platform
cp .env.example .env
```

### 2. Generate JWT key pair
```bash
mkdir keys
openssl genrsa -out keys/private.pem 2048
openssl rsa -in keys/private.pem -pubout -out keys/public.pem
```

### 3. Start all services
```bash
docker compose -f infrastructure/docker/docker-compose.yml up -d
```

Services available at:
| Service | URL |
|---|---|
| FastAPI API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/api/docs |
| MinIO Console | http://localhost:9001 |

### 4. Run database migrations
```bash
# From the api container or locally with venv activated:
alembic upgrade head
```

### 5. Start the frontend (separate terminal)
```bash
cd apps/web
npm install
npm run dev
```

Frontend available at: http://localhost:3000

---

## How to Run Tests

```bash
# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate   # Windows
source .venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Generate test JWT keys
mkdir keys
openssl genrsa -out keys/private.pem 2048
openssl rsa -in keys/private.pem -pubout -out keys/public.pem

# Run tests
pytest apps/api/modules apps/api/tests -v --cov=apps/api/modules

# Run with HTML coverage report
pytest apps/api/modules --cov=apps/api/modules --cov-report=html
# Open htmlcov/index.html
```

Tests use SQLite in-memory (no Docker needed for unit/integration tests).

---

## Environment Variables

See [`.env.example`](.env.example) for the full list of required variables.

Key variables:

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://...` |
| `REDIS_URL` | Redis connection | `redis://localhost:6379/0` |
| `JWT_PRIVATE_KEY_PATH` | Path to RSA private key PEM | `./keys/private.pem` |
| `JWT_PUBLIC_KEY_PATH` | Path to RSA public key PEM | `./keys/public.pem` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT access token TTL | `15` |
| `CORS_ORIGINS` | Comma-separated allowed origins | `http://localhost:3000` |

---

## Architecture

```
apps/
  api/          FastAPI backend (modular monolith)
  web/          Next.js 14 frontend (App Router)

services/
  worker/       Celery async task workers

packages/
  ml-core/      Shared ML/AI logic
  shared-types/ TypeScript types from OpenAPI

infrastructure/
  docker/       Docker Compose + Dockerfiles
  github-actions/ CI/CD pipelines
  kubernetes/   Production Kubernetes manifests
```

See [`docs/adr/`](docs/adr/) for architecture decisions.

---

## Phase Status

| Phase | Name | Status |
|---|---|---|
| 0 | Foundation (Auth + Projects + Infra) | 🔨 In Progress |
| 1 | Evaluation Platform | ⏳ Pending |
| 2 | Regression Detection | ⏳ Pending |
| 3 | Dataset Intelligence | ⏳ Pending |
| 4 | AutoML | ⏳ Pending |
| 5 | Explainability | ⏳ Pending |
| 6 | Conversational Analytics | ⏳ Pending |
| 7 | MLOps | ⏳ Pending |
| 8 | Enterprise Features | ⏳ Pending |

---

## API Reference

Auto-generated API docs at `http://localhost:8000/api/docs` (Swagger UI) or `http://localhost:8000/api/redoc`.

Base path: `/api/v1`
Auth: `Authorization: Bearer <access_token>`

---

## Contributing

This project follows [Conventional Commits](https://www.conventionalcommits.org/):
- `feat:` new feature
- `fix:` bug fix
- `refactor:` code change with no behavior change
- `test:` adding tests
- `docs:` documentation only

Branch naming: `feature/<phase>-<short-description>` (e.g., `feature/phase1-golden-dataset-crud`)

All changes go through a reviewed PR before merge to `main` per Section 23.7.
