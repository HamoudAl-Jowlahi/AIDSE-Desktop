# AIDSE Desktop — Architecture and Implementation

A record of what this system is, how its parts fit together, and where the
sharp edges are. Written to be checked: where a claim could be wrong, it says
how to verify it.

The previous version of this document described a multi-tenant SaaS platform
with Celery workers, a Redis broker, PostgreSQL and a "~10–15 MB" Tauri
installer, and reported 208 passing tests. None of that is true of this
repository any more, and the installer figure was never true of anything.

---

## 1. What it is

A desktop application for dataset work and machine learning: profile a
dataset, prepare it, train candidate models with hyperparameter search,
explain what the best one learned, and evaluate model outputs against curated
golden datasets.

Everything runs on the machine it is installed on. There is no server, no
account, and no tenant. The only outbound request the application makes on its
own is a daily check for a new release; an LLM provider is contacted only if
the user configures one.

This began as a hosted platform and was forked when running it in the cloud
became too expensive to justify. The fork explains most of the oddities a
reader will hit: `DATABASE_URL` still defaults to a PostgreSQL URL, the auth
module still issues JWTs to a single local user, and configuration still
carries knobs no desktop install will ever turn.

---

## 2. How the pieces fit

```
┌──────────────────────────────────────────────────────────────┐
│ Tauri shell (Rust) — src-tauri/                              │
│                                                              │
│  · picks a free loopback port, generates a 256-bit token     │
│  · starts the backend as a child process and supervises it   │
│  · stops it on exit                                          │
│  · checks GitHub Releases for a signed update                │
│                                                              │
│  ┌────────────────────────┐      ┌────────────────────────┐  │
│  │ WebView                │      │ backend child process  │  │
│  │ Next.js static export  │─────▶│ FastAPI + uvicorn      │  │
│  │ apps/web/out           │ HTTP │ 127.0.0.1:<port>       │  │
│  │                        │ +tok │                        │  │
│  └────────────────────────┘      └───────────┬────────────┘  │
└──────────────────────────────────────────────┼───────────────┘
                                               │
                    ┌──────────────────────────┼──────────────────────┐
                    ▼                          ▼                      ▼
            ┌───────────────┐        ┌──────────────────┐   ┌──────────────────┐
            │ SQLite        │        │ scikit-learn,    │   │ SHAP             │
            │ SQLAlchemy 2  │        │ XGBoost, LightGBM│   │ explanations     │
            │ Alembic       │        │ CatBoost, Optuna │   │                  │
            └───────────────┘        └──────────────────┘   └──────────────────┘
```

The window does not know where the backend is until it asks. On first load the
frontend calls the shell's `get_sidecar_config` command and receives the host,
port and token; every request carries the token in `X-AIDSE-Internal-Token`.
Requests without it are refused with 403, `/health` excepted.

This matters because loopback is not a security boundary: anything running as
the same user can reach `127.0.0.1`. The token is what a process needs, and it
exists only in the memory of the shell and the backend it started.

**Verify it**: launch the built shell, read the backend's command line for its
port and token, and try the API with no token, a wrong token, and the real one.
Expect 403, 403, 200.

---

## 3. Backend modules

`apps/api/modules/`, a modular monolith — one process, one database, separated
by package rather than by service.

| Module | What it does |
|---|---|
| `auth` | Local user, bcrypt master password, RS256 JWTs, the app-lock check |
| `projects` | Projects and their cascade to everything below |
| `datasets` | Ingestion (CSV, XLSX, Parquet, JSON), profiling, quality, preparation, versioning, target-column suggestion |
| `automl` | Optuna search over candidate algorithms; trials, leaderboard, metrics |
| `explainability` | SHAP values and feature importance for a chosen trial |
| `evaluation` | Golden datasets, evaluation runs, baselines, regression detection |
| `conversational` | The analyst chat, and provider credentials |
| `reporting` | Report generation |
| `system` | Desktop settings, diagnostics, hardware limits |

`comparison`, `deployment` and `monitoring` used to sit alongside these. Each
was a single empty `__init__.py` that nothing imported, and they are gone.

### AutoML

The default candidate sets are deliberately small:

```python
FOCUSED_CLASSIFICATION = ["logistic_regression", "random_forest", "xgboost", "svm"]
FOCUSED_REGRESSION     = ["linear_regression", "random_forest", "xgboost"]
```

LightGBM and CatBoost are implemented and selectable, just not default.

Optuna runs each trial under a try/except, so one algorithm failing to fit
leaves the rest of the run intact rather than killing it, and the best trial is
chosen by score rather than by position in the list.

Training runs in-process, in a worker thread so the event loop stays
responsive. There is no other route. It used to try a Celery broker first,
which is what made creating an experiment take twenty seconds on a machine
without Redis — the broker dial was bounded, but the Redis result backend
retried twenty times on its own. The worker package and both dependencies are
gone.

### Evaluation

Four scoring strategies, in `modules/evaluation/scoring.py`:
`exact`, `regex`, `semantic`, `llm_judge`. A run can be compared against a
designated baseline to separate genuine regressions from flaky cases.

`llm_judge` is the one strategy that needs a configured provider. Without one
it is unavailable rather than silently degraded.

---

## 4. Data, and what is actually protected

The database is a plain SQLite file under the application data directory.
Datasets are files beside it.

**Encrypted**: stored provider API keys, with Fernet, under a 256-bit secret
generated on first run and kept in the OS credential store (Windows Credential
Manager, macOS Keychain, Linux Secret Service). If the credential store cannot
be written, the vault refuses to continue rather than falling back to a
throwaway key.

**Not encrypted**: the database file, datasets, project files, reports.

Earlier versions of the onboarding wizard, the landing page and the docs all
claimed AES-256 SQLCipher encryption of the whole database. The code that was
supposed to provide it was a `PRAGMA key` statement against stock SQLite, which
does nothing. The claim has been removed everywhere and a test now fails if it
returns. Full-disk encryption is the honest answer for data at rest.

The app lock is a lock, not encryption: it keeps someone at the keyboard out of
the workspace. It does not protect files from a program running as the same
user.

### Schema

Alembic owns the schema. A squashed baseline
(`20260912_0013_2107bfe05bb2`) matches the models, using `sa.Uuid()` so SQLite
gives UUID columns TEXT affinity and foreign keys resolve.

The lifespan used to call `Base.metadata.create_all` on every start. That made
a failed migration invisible: tables appeared anyway, `alembic_version` stayed
empty, and the next real migration had nothing to upgrade from — which is the
state every install was in. `create_all` is gone; if the schema is missing now,
migrations failed, and that is loud.

**Verify it**: point `AIDSE_DATA_DIR` at an empty directory, run the lifespan,
and check the table count and `alembic_version`.

---

## 5. Frontend

Next.js 15 App Router, exported statically — the shell serves files from disk,
so there is no Node process at runtime.

Fonts are vendored as seven local `woff2` files. They were loaded from Google's
CDN, which meant an offline desktop app rendered in fallback faces and made a
network request on every launch.

Both themes work; the app is no longer locked to dark. The toggle sits in the
top bar, where a duplicate settings icon used to be.

The notification page is backed by a real store (`lib/notifications.ts`,
localStorage, `useSyncExternalStore`), so the badge and the page always agree.
It previously held a `useState([])` that nothing ever wrote to, which rendered
a permanent empty state no matter what happened in the app.

---

## 6. Packaging and updates

PyInstaller bundles the backend in onedir form: a launcher stub plus an
`_internal` tree holding the Python DLL it loads at startup. Tauri ships that
whole directory as a bundled resource — `externalBin` copies a single file and
could never have worked.

The NSIS installer is about 236 MB, down from 353 MB. Python and the ML
libraries are ~848 MB unpacked and no packaging choice changes that; what Tauri
buys is the token boundary, a native window, lower memory, and no dependency on
an installed browser.

Updates come from GitHub Releases. Each installer is signed with a minisign
key whose public half is compiled into the shell, and an installer that does
not verify is refused. The check runs once a day, stays silent on failure, and
surfaces as a corner toast rather than a modal. See
[`docs/releasing.md`](docs/releasing.md).

---

## 7. Tests

296 tests, roughly four minutes, plus 8 Rust tests for the shell.

The number is not the point. Several of these files used to assert against
mocks they had defined themselves — one "sidecar restart limit" test defined a
counter inside its own body and never imported the manager it claimed to
cover. The suite was green while the installer shipped an incomplete file set,
migrations did nothing on every machine, the restart policy was never called,
and the bundled app could not find its own backend.

So the standard here is: after writing a test, break the code it covers and
confirm it fails. Every test added during the audit was checked that way, and
the commit messages name the mutation used.

Two defects in that list were found only by launching the built application.
Both produced a clean, green, warning-free build.

---

## 8. Known gaps

- `mlflow` is bundled (996 submodules) and writes to `mlruns/`, but the only
  user-visible output is an un-clickable run id in the experiments table. Kept
  deliberately; worth either surfacing or removing.
- `DATABASE_URL` still defaults to a PostgreSQL URL. The backend overrides it
  at startup, so this only bites someone running the API by hand.
- The refresh token is stored in a cookie readable by JavaScript.
- The frontend has 76 eslint warnings, mostly `any` and unused bindings.
- There is no macOS or Linux build; the PyInstaller spec is Windows-specific.
