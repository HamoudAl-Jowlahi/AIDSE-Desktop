# AIDSE Desktop

**AI Data Scientist & Evaluation Platform** — dataset profiling and preparation,
AutoML training, evaluation against golden datasets, and SHAP explainability,
running entirely on the machine it is installed on.

This repository is the desktop application. It was forked from a multi-tenant
web platform, and the fork is worth knowing about: anything here that still
talks about tenants, Docker, PostgreSQL or object storage is a leftover, not a
feature.

---

## What it is

| | |
|---|---|
| Shell | Tauri v2 (Rust) with the system WebView |
| Frontend | Next.js 15 App Router, static export, React 19, Tailwind v4 |
| Backend | FastAPI, launched by the shell as a child process |
| Database | SQLite via async SQLAlchemy 2, migrated by Alembic |
| ML | scikit-learn, XGBoost, LightGBM, CatBoost, Optuna, SHAP |

The backend listens on loopback on a port the OS assigns at launch, and the
shell hands it a fresh 256-bit token that every request must carry. A process
that cannot read the shell's memory cannot call the API, even though it is
running as the same user.

**What is encrypted:** stored provider API keys, with Fernet, under a
per-install secret in the OS credential store. **What is not:** the database
file itself, your datasets, and project files. Use full-disk encryption for
those. See [`docs/threat_model.md`](docs/threat_model.md).

---

## Running it during development

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt -r requirements-dev.txt
npm install
npm --prefix apps/web install
```

JWT signing keys are read from `keys/`. Generate them once:

```bash
mkdir -p keys
openssl genrsa -out keys/private.pem 2048
openssl rsa -in keys/private.pem -pubout -out keys/public.pem
```

Then, from the repository root:

```bash
npm run dev
```

That starts the Next.js dev server and opens the Tauri window against it. The
window launches the backend itself — there is no separate command for it, and
starting one by hand only produces a second backend the window ignores.

---

## Tests

```bash
.venv/Scripts/pytest
```

296 tests, about four minutes, no network and no Docker. `pyproject.toml`
points pytest at `apps/api/modules` and `apps/api/tests`.

Rust tests for the shell:

```bash
cargo test --manifest-path src-tauri/Cargo.toml
```

A note on what the tests are for. Several files here once asserted against
mocks they had defined themselves, so they passed while the thing they named
was broken — the installer shipped an incomplete file set, migrations silently
did nothing, and the sidecar restart policy was unit-tested but never called.
When you add a test, break the code it covers and confirm it fails. A test that
cannot fail is worse than none, because it is read as coverage.

---

## Building the installer

Requires the Rust toolchain and MSVC build tools.

```bash
.venv/Scripts/pyinstaller infrastructure/desktop/sidecar.spec --distpath dist --noconfirm
npm run build
```

The first command bundles the Python backend into `dist/aidse-backend` — a
launcher stub plus an `_internal` tree it loads its Python DLL from, which is
why it ships as a resource directory rather than a single binary. The second
builds the frontend and produces
`src-tauri/target/release/bundle/nsis/`, roughly 236 MB.

Most of that size is Python and the ML libraries, and no packaging choice
changes it.

Releases and the update mechanism: [`docs/releasing.md`](docs/releasing.md).

---

## Layout

```
apps/
  api/            FastAPI backend (modular monolith)
    db/           models, session, Alembic migrations, secret vault
    modules/      auth, projects, datasets, automl, evaluation,
                  explainability, conversational, reporting
  web/            Next.js frontend; `out/` is the static export the shell serves

src-tauri/        Rust shell: window, backend supervision, updater
infrastructure/
  desktop/        PyInstaller spec for the backend bundle
docs/             threat model, privacy guide, release process, ADRs
keys/             JWT PEMs — generated locally, never committed
```

---

## Configuration

`.env.example` lists what can be set. The defaults are correct for a desktop
install; most of these exist for development.

| Variable | Description | Default |
|---|---|---|
| `AIDSE_DATA_DIR` | Where the database and datasets live | OS app-data directory |
| `DATABASE_URL` | SQLAlchemy URL. The shell's backend sets this to SQLite under `AIDSE_DATA_DIR` at startup; the bare default is a leftover PostgreSQL URL that only applies if you run the API by hand without `AIDSE_DESKTOP_MODE=1` | see note |
| `JWT_PRIVATE_KEY_PATH` | RSA private key PEM | `./keys/private.pem` |
| `JWT_PUBLIC_KEY_PATH` | RSA public key PEM | `./keys/public.pem` |
| `LOCAL_TRAINING_FALLBACK` | Run AutoML in-process | `true` |
| `RATE_LIMIT_ENABLED` | Throttle auth endpoints | `true` |

---

## Contributing

[Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`,
`refactor:`, `test:`, `docs:`.

Say what changed and why it was wrong before. A commit message that only
names the file teaches the next reader nothing.
