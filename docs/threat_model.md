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
- **Storage**: Saved to local SQLite database encrypted at rest via AES-256 SQLCipher (`aidse.db`).
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

1. **Loopback Binding**: FastAPI/Uvicorn binds strictly to `127.0.0.1` on a dynamically allocated free port (`find_free_loopback_port()`). Public binding (`0.0.0.0`) is enforced as forbidden and blocked by runtime configuration guards.
2. **Internal Session Token**: Every HTTP request between Tauri frontend and FastAPI sidecar is authenticated with a cryptographically strong 256-bit token (`X-AIDSE-Internal-Token`) generated at startup and shared strictly via in-memory process environment. Unauthenticated requests are rejected with `403 Forbidden`.
3. **Data Encryption at Rest**: SQLite database is encrypted using SQLCipher. The encryption key is generated at first launch and stored securely in OS-native credential storage (Windows Credential Manager / macOS Keychain / Linux Secret Service).
