# ADR-001: Modular Monolith over Microservices for AIDSE MVP
**Date:** 2026-06-28
**Status:** Accepted
**Section Reference:** Section 9.3 — Microservice Boundaries

---

## Context

AIDSE is being built by a solo founder using agent-augmented development. The platform covers 11 functional modules (Dataset Intelligence, AutoML, Evaluation, Regression Detection, Monitoring, etc.).

Two architectural options were considered:

1. **Microservices from day one**: each module as an independently deployable service with its own DB
2. **Modular Monolith**: all modules co-deployed in a single FastAPI application, with module boundaries enforced by code structure (folder contract: `router.py / schemas.py / service.py / models.py / tests/`)

---

## Decision

**Modular Monolith** for MVP through V1 (Phases 0-5).

---

## Consequences

### Positive
- **Solo build velocity**: no service mesh, no distributed tracing, no inter-service authentication to solve in Phase 0. One docker compose up brings up everything.
- **Shared data model**: The core data model (Project → Dataset → Experiment → Evaluation) is highly relational. A monolith avoids the distributed join problem that microservices would introduce for something as fundamental as "list all evaluations for this project."
- **Shared codebase**: Agent-generated code is easier to audit and maintain when it lives in one repo with one test suite and one CI pipeline.
- **Future extraction path preserved**: The folder contract (`router.py`, `service.py`, etc.) enforces clean module boundaries that survive microservice extraction. Each module's service.py has no imports from other modules' service.py — only through the shared DB.

### Negative / Trade-offs
- **Scaling granularity**: Cannot scale evaluation processing independently from the API. Mitigated by putting all CPU-intensive work in Celery workers (separate containers) rather than the API process.
- **Deployment coupling**: A bug in AutoML training code can (in theory) take down the Evaluation API. Mitigated by comprehensive testing and feature flags.

### Extraction Triggers (when to extract to microservices)
Per Section 9.3:
- **Evaluation module**: Extract if eval request volume becomes the dominant load. Most likely candidate given MVP wedge.
- **Training/AutoML**: Extract when GPU-optimized worker pools are needed.
- **Auth**: Extract if multi-tenant scale requires isolated auth service.

---

*ADR format: Context → Decision → Consequences. Section 23.6.*
