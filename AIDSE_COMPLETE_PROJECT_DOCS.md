# 🚀 AIDSE Platform — Complete System Architecture & Implementation Report

---

## 📌 Executive Summary

**AIDSE (AI Data Scientist & Evaluation Platform)** is an enterprise-grade, unified platform for automated machine learning (**AutoML**), dataset intelligence, explainable AI (**XAI / SHAP**), model evaluation, and **regression detection**.

This document outlines the complete technical architecture, implemented modules, bug fixes, algorithmic designs, zero-config deployment packages, and the strategic roadmap for Desktop App conversion.

---

## 🏗️ Technical Architecture & Tech Stack

```
                     ┌──────────────────────────────────────────┐
                     │          Next.js 15 / React 19           │
                     │    Glassmorphic Dark Mode UI (Web)       │
                     └────────────────────┬─────────────────────┘
                                          │  REST API (JSON)
                                          ▼
                     ┌──────────────────────────────────────────┐
                     │            FastAPI (Python)              │
                     │    Async Event-Driven REST Endpoints    │
                     └───────┬──────────────────────────┬───────┘
                             │                          │
           ┌─────────────────┴─────────┐      ┌─────────┴────────────────┐
           ▼                           ▼      ▼                          ▼
┌────────────────────┐    ┌─────────────────┐ ┌────────────────┐ ┌──────────────┐
│  Optuna / AutoML   │    │  SHAP XAI Engine│ │ Async SQLAlchemy│ │ Local Worker │
│  XGBoost/LightGBM  │    │  Feature Imp.   │ │ SQLite / Postgres│ │ Asyncio Thread│
└────────────────────┘    └─────────────────┘ └────────────────┘ └──────────────┘
```

### 💻 Stack Components:
- **Backend API Framework**: FastAPI (Python 3.11–3.14)
- **Database Layer**: SQLAlchemy 2.0 (Async) + Alembic migrations + SQLite / PostgreSQL
- **AutoML Engine**: Optuna, Scikit-Learn, XGBoost, LightGBM, CatBoost
- **Explainable AI (XAI)**: SHAP (SHapley Additive exPlanations)
- **Frontend UI Framework**: Next.js 15 (App Router), React 19, Tailwind CSS v4, Lucide & Material Symbols
- **Task Scheduling**: Local Async Fallback Runner (`asyncio.create_task` + `asyncio.to_thread`) + Celery / Redis support

---

## ⚙️ Core Implemented Modules & Capabilities

### 1. 🔑 Auth & Security Module (`apps/api/modules/auth`)
- **Secure Authentication**: Password pre-hashing (SHA-256 + Bcrypt) & RS256 JWT tokens.
- **Param Order Fix**: Fixed non-default parameter ordering syntax error in `refresh` endpoint (`apps/api/modules/auth/router.py`).
- **Flexible Auth Modes**: Supports full JWT authentication + zero-config Evaluator Mode for instant testing.

### 2. 📊 Dataset Intelligence & Target Detection (`apps/api/modules/datasets`)
- **Multi-Format Ingestion**: Full support for CSV, XLSX, Parquet, and JSON datasets.
- **Automated Data Profiling**: Detects missing values, IQR outliers, class imbalance, and data leakage risks.
- **Intelligent Target Column Suggestion**: Heuristic algorithm (`task_detection.py`) analyzes column names, cardinalities, and variance to automatically rank candidate target columns and detect problem types (**Classification** vs. **Regression**).
- **Transformation History**: Tracks version lineage and data preparation transformations (`transform_dataset_version`).

### 3. 🤖 ML Lab & AutoML Engine (`apps/api/modules/automl`)
- **Hyperparameter Optimization**: Powered by **Optuna** trial tuning across 5 algorithms (*Random Forest, Logistic/Linear Regression, XGBoost, LightGBM, CatBoost*).
- **Dynamic Leaderboard**: Ranks model trials dynamically using primary metrics (*Accuracy, F1-Macro, Precision, Recall, ROC-AUC, R², RMSE, MAE*).
- **Non-Blocking Execution**: Optuna fitting runs in separate worker threads (`asyncio.to_thread`) to prevent blocking FastAPI's main event loop.
- **Local Fallback Dispatcher**: Catches Kombu/Redis connection timeouts (`connect_timeout=1`) and executes training in background local tasks (`_run_automl_async`) seamlessly without requiring Redis or Docker containers.

### 4. 🔍 Model Explainability (SHAP / XAI)
- **Feature Importance & SHAP Values**: Calculates SHAP summary contributions for top trials, allowing users to understand the exact feature impact behind predictions.

### 5. 🎯 AI Evaluation Engine & Golden Datasets (`apps/api/modules/evaluation`)
- **Evaluation Runs**: Evaluates model predictions against curated **Golden Datasets**.
- **4 Scoring Strategies**:
  1. *Exact Match*: Strict text/numeric equality.
  2. *Regex Pattern*: Pattern-based evaluation.
  3. *Semantic Similarity*: Embedding/similarity scoring.
  4. *LLM Judge*: Model-assisted evaluation.
- **Regression Gate Detection**: Compares evaluation runs against designated **Baselines** to detect passing cases, failing cases, flaky tests, and overall regression status.

### 6. 🎨 Frontend UI/UX Refinements (`apps/web`)
- **Forced Dark-Only Theme**: Enforced `forcedTheme="dark"` across the entire app for a consistent, premium glassmorphic aesthetic.
- **Global Search Palette (`GlobalSearchModal.tsx`)**: Instant fuzzy search across Projects, Datasets, and Pages with `Esc` shortcut and real-time navigation.
- **Notifications Center (`/notifications`)**: Dedicated notifications page with clean empty states.
- **Interactive Project Selector**: Dynamic project dropdown on the dashboard header updating dataset counts, quality issues, model runs, and recent analyses in real time.
- **Project Deletion (Delete Project)**: Added `DELETE /api/v1/projects/{id}` backend endpoint with cascade relationships (`cascade="all, delete-orphan"`) and a red Delete button with confirmation modals on the UI.

---

## 🛠️ Verification & Test Suite Results

- **Total Test Cases**: **208 Automated Unit & Integration Tests**
- **Test Suite Result**: **100% PASSED (208/208 Passed)**

```bash
================ 208 passed, 86 warnings in 160.04s (0:02:40) =================
```

---

## 📦 Academic Evaluation Package (`AIDSE PLATFORM`)

Created a lightweight standalone copy at `C:\Users\Hamoud KJ\Desktop\AI Projects  Researches\AIDSE PLATFORM`:
- **Ultra-Minimal Size**: Reduced total folder size to **1.27 MB** (excluding `.venv` and `node_modules`).
- **Zero-Config Auto-Auth**: Bypasses login prompts so the evaluator opens directly into the active dashboard.
- **Self-Healing Launchers**:
  - `start-backend.bat`: Auto-detects Python, creates `.venv`, copies `.env.example`, runs SQLite migrations (`alembic upgrade head`), and starts Uvicorn.
  - `start-frontend.bat`: Auto-detects `node_modules`, runs `npm install` if missing, and launches Next.js on port 3000.
  - `run_test.bat`: Executes the 208 automated pytest suite.
- **Complete Evaluation README**: Includes a comprehensive step-by-step teacher guide.

---

## 🛡️ Strategic Roadmap: Desktop App Conversion (Tauri vs Electron)

### Strategic Architecture Recommendation:
Converting **AIDSE** into a **Local-First Desktop Application** provides **100% Data Privacy & Security** (data never leaves the user's computer) and **$0 Cloud Server Costs** by leveraging the user's local CPU/GPU.

### Technology Comparison:

| Feature | ⚡ Tauri (v2) — RECOMMENDED | 📦 Electron.js |
| :--- | :--- | :--- |
| **Engine** | Rust + Native System WebView (WebView2/WebKit) | Chromium Browser + Node.js runtime |
| **Binary Installer Size** | 🪶 **~10–15 MB** | 🐘 **~100–150 MB** |
| **RAM Consumption** | 💚 **~30–80 MB** (Leaves 95% RAM for ML) | 🔴 **~200–500 MB** |
| **Security Architecture** | 🔒 Memory-safe Rust, IPC capability isolation | ⚠️ Requires manual security tuning |

**Verdict**: **Tauri** is the optimal choice for AIDSE as it leaves maximum RAM and system resources available for heavy Machine Learning calculations (Optuna & SHAP).

---
*Report Generated — AIDSE Platform Documentation*
