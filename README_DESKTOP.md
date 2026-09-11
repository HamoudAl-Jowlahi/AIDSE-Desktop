# 🚀 AIDSE Desktop Application — Standalone Repository

Welcome to the **AIDSE Desktop** standalone repository. This codebase represents the local-first desktop version of the **AIDSE (AI Data Scientist & Evaluation Platform)**.

All data processing, dataset intelligence, AutoML model tuning (Optuna/Scikit-Learn/XGBoost/LightGBM/CatBoost), explainable AI (SHAP), and golden dataset evaluation run **100% locally on the user's computer**.

---

## 🏗️ Architecture & Tech Stack

- **Desktop Engine**: Tauri v2 (Rust shell) + Native WebView (WebView2 / WebKit)
- **Backend API**: FastAPI (Python 3.11–3.14) running as a Tauri sidecar process
- **Database**: Async SQLAlchemy 2.0 over local SQLite
- **Security**: stored provider API keys are encrypted (Fernet) with a per-install 256-bit secret held in the OS credential store (Windows Credential Manager / macOS Keychain / Linux Secret Service); the API binds to loopback only (`127.0.0.1`).
- **Frontend**: Next.js 15 (App Router, static export), React 19, Tailwind v4, forced dark glassmorphic theme.

---

## ⚡ Quick Start Guide

### Step 1: Install Dependencies
```bash
# Set up Python virtual environment
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt

# Install Web Dependencies
cd apps/web
npm install
cd ../..
```

### Step 2: Launch Application
```bash
# Terminal 1 — Start FastAPI Backend Sidecar:
.\start-backend.bat

# Terminal 2 — Start Frontend UI:
.\start-frontend.bat
```
Open your browser at **`http://localhost:3000`** to complete the first-run onboarding sequence.

### Step 3: Run Desktop App via Tauri
```bash
cd apps/web
npm run build
cd ../..
npx tauri dev
```

---

## 🧪 Automated Test Suite

To execute the automated test suite:
```bash
.\.venv\Scripts\pytest
```

---

## 🛡️ Privacy & Threat Model
For security audit details and threat model analysis, see:
- [docs/threat_model.md](docs/threat_model.md)
- [docs/local_privacy_guide.md](docs/local_privacy_guide.md)
- [docs/smoke_test_vm.md](docs/smoke_test_vm.md)
