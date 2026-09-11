# AIDSE Desktop — Threat Model & Security Audit Summary
**Phase 8 — Distribution & Hardening Review**

## Executive Summary
AIDSE is engineered as a **local-first, privacy-preserving desktop application**. Data processing, dataset intelligence, AutoML model fitting (Optuna/Scikit-Learn/XGBoost/LightGBM/CatBoost), explainable AI (SHAP), and golden dataset evaluation take place **100% locally** on the user's computer.

This document enumerates all potential data exit paths, verifying that each is either completely eliminated or explicitly opt-in with clear user-facing disclosure.

---

## Data Exit Path Inventory

### Path 1: Datasets, Versions & Data Preprocessing
- **Data Flow**: Ingestion, profiling, target detection, transformations, quality checks, and export.
- **Location**: Executed entirely within local Python FastAPI sidecar process.
- **Storage**: Saved to a local SQLite database (`aidse.db`) in the per-user data directory. The database file itself is **not** encrypted — see "Data at rest" below.
- **Verdict**: 🔒 **100% Local-Only**. Zero network egress.

### Path 2: AutoML Model Training & Hyperparameter Tuning
- **Data Flow**: Optuna trial optimization, Scikit-Learn / XGBoost / LightGBM / CatBoost model fitting.
- **Location**: Executed in local worker threads (`asyncio.to_thread`) on local CPU/GPU.
- **Verdict**: 🔒 **100% Local-Only**. Zero network egress.

### Path 3: Explainable AI (SHAP Feature Importance)
- **Data Flow**: Calculating SHAP values, tree explainers, and feature contributions.
- **Location**: Executed locally using `shap` library.
- **Verdict**: 🔒 **100% Local-Only**. Zero network egress.

### Path 4: Golden Dataset Evaluation — Standard Strategies
- **Strategies**: `exact` match, `regex` pattern match, `semantic` similarity.
- **Location**: Calculated inside local evaluation engine (`apps/api/modules/evaluation`).
- **Verdict**: 🔒 **100% Local-Only**. Zero network egress.

### Path 5: Golden Dataset Evaluation — LLM Judge Strategy (OPT-IN ONLY)
- **Data Flow**: Evaluates test case prompt and model output using external LLM provider (e.g. OpenAI / Anthropic API).
- **Control & Disclosure**:
  - Disabled by default (`LLM_PROVIDER: "none"`).
  - Prominently disclosed in Step 5 of First-Run Onboarding and in Settings.
  - Requires user to explicitly supply an API key and invoke LLM Judge strategy.
- **Verdict**: ⚠️ **Explicit Opt-in Only**. User is informed before any payload leaves the machine.

---

## Local Network Isolation Controls

1. **Loopback Binding**: FastAPI/Uvicorn binds strictly to `127.0.0.1`. Public binding (`0.0.0.0`) is rejected at startup by `validate_host_binding()`. The port is currently **fixed at 8010**, falling forward to the next free port when taken — it is not randomized. A `find_free_loopback_port()` helper exists but is not yet on the startup path.

2. **Internal Session Token**: ⚠️ **Not active.** `InternalTokenMiddleware` is implemented and enforces `X-AIDSE-Internal-Token` correctly *when* `AIDSE_INTERNAL_TOKEN` is set — but nothing sets it. The launcher passes no token and the Tauri shell hardcodes an empty one, so the middleware currently passes every request through. Combined with desktop mode's automatic admin session, **any process running as the same user can call the full API**. Scheduled for the Tauri integration work; until then this is the application's main local-privilege gap.

3. **Data at rest**: The SQLite database is **not** encrypted; the file carries a standard `SQLite format 3` header and opens with any SQLite client. Whole-database encryption would require SQLCipher and a different driver, and is not implemented.

   What *is* protected: sensitive column values — today the LLM provider API key — are encrypted with Fernet (AES-128-CBC + HMAC) under a 256-bit per-install secret stored in the OS credential store (`apps/api/db/vault.py`). Copying the database to another machine does not expose them.

   Users should rely on their OS account plus full-disk encryption for the dataset contents themselves.
