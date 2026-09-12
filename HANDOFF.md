# AIDSE Desktop — Audit & Remediation Handoff

**Written:** 12 September 2026
**Purpose:** Continue this work in a fresh session with no prior context.
**Repo:** `C:\Users\Hamoud KJ\Desktop\AI Projects  Researches\AIDSE Project\aidse-desktop`

---

## 1. What this project is

**AIDSE** — an "AI data scientist" workspace for tabular data. Upload a CSV/XLSX →
profile it → see quality issues → clean it → train and compare ML models →
explain them with SHAP. A second track evaluates LLM outputs against curated
"golden datasets" and detects regressions between runs.

It began as a multi-tenant **web platform** (`../aidse-platform`, the sibling
folder). Around Sep 2026 the owner forked it to `aidse-desktop` because cloud
hosting costs were too high. The pivot was cost-driven, not technical — so a
lot of server-era machinery (Celery, Redis, MinIO, Postgres, Kubernetes) is
**vestigial, not deliberate**. Treat it as removal candidates.

### Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 15 (App Router, **static export**), React 19, Tailwind v4 |
| Backend | FastAPI + SQLAlchemy 2 async + SQLite (`aiosqlite`) |
| ML | scikit-learn, XGBoost, LightGBM, CatBoost, Optuna, SHAP, MLflow |
| Packaging | PyInstaller → `dist/aidse-backend`, Inno Setup → installer |
| Desktop shell | Tauri v2 — **present but NOT wired up** (see §5) |

### How it actually runs today

```
Launch-AIDSE.vbs
  → dist\aidse-backend\aidse-backend.exe   (FastAPI, port 8010)
  → msedge.exe --app="http://127.0.0.1:8010"
```

**The shipped app is Microsoft Edge in kiosk mode, not Tauri.** `src-tauri/`
exists but `main.rs` never spawns the sidecar and hardcodes an empty token.
The backend serves the static frontend itself (`apps/api/main.py` mounts
`apps/web/out`).

### Key paths

```
apps/api/          FastAPI backend (9 live modules + 3 empty stubs)
apps/web/          Next.js frontend
src-tauri/         Tauri shell (stub)
infrastructure/    docker/, github-actions/ (web-era leftovers)
alembic.ini        Migration config — MUST sit next to apps/
HANDOFF.md         This file
```

### Running it

```bash
# Backend (dev)
AIDSE_DESKTOP_MODE=1 AIDSE_DATA_DIR=/tmp/scratch PYTHONPATH=$PWD \
  ./.venv/Scripts/python.exe apps/api/sidecar_entry.py --host 127.0.0.1 --port 8021

# Frontend build (backend serves apps/web/out)
cd apps/web && npm run build

# Tests
./.venv/Scripts/python.exe -m pytest -q
```

**User data lives in `%LOCALAPPDATA%\AIDSE-Desktop\`** — `aidse.db`, `storage/`,
`mlruns.db`, `settings.json`. A backup of the pre-audit state is at
`../_backup_20260911/`.

---

## 2. The one thing to understand before changing anything

Nearly every defect found in this audit was an **unverified claim** — a feature
that was documented, tested green, and did not work.

The test suite did not catch a single one, because several test files asserted
against **mocks, local closures, and config-file strings** rather than the
running system. `test_sqlcipher_encryption.py` checked that a file of random
bytes did not start with the SQLite magic header — it passed for the entire
period the shipped database was plaintext.

**Therefore:** do not trust this repo's docs, or a green test run, as evidence
that something works. Run it. Every fix below was verified by executing the real
path, and where a test could not reproduce the original fault, that is stated
rather than papered over.

---

## 3. Work completed (12 commits)

```
a076702  Phase 3 (part 1): spawn the sidecar, and give it a real token and port
3249246  Search every project, and add a handoff document
7e02e8f  Reach the light theme, and delete a page that invented its own results
492519a  Make the desktop UI work offline, and replace the decorative parts with real ones
26fb9c5  Repair explainability, training resilience, and identifier leakage
041ec90  Fix four faults found by actually running the application
99c44e9  Remove an app lock that never locked anything, and two false encryption claims
a5174b1  Stop discarding the confusion matrix and per-class breakdown
3e59566  Replace the mock-asserting desktop tests with ones that fail when broken
e818608  Make migrations actually run, and squash the chain onto a working baseline
fa4d6de  Phase 1: close the critical security and data-loss findings
4ab746b  Baseline: AIDSE Desktop as-is before the audit remediation
```

Read any commit message in full (`git show <sha>`) — they carry the reasoning,
not just the change.

### Phase 0 — Safety net ✅
- `git init` (the project had **no version control at all**), correct `.gitignore`
- Backed up live user data to `../_backup_20260911/`

### Phase 1 — Security & data loss ✅ (`fa4d6de`)
| Fixed | Detail |
|---|---|
| **Silent `DROP TABLE` on every launch** | `lifespan` dropped any table whose DDL contained `"UUID"` anywhere |
| **Database was not encrypted** | Docs claimed AES-256 SQLCipher. `PRAGMA key` is a **no-op** on stdlib `sqlite3`. Proven by opening `aidse.db` with plain `sqlite3` |
| **Real field encryption** | Provider API keys now encrypted with a per-install 256-bit secret in Windows Credential Manager (`apps/api/db/vault.py`) |
| `keyring` missing | Imported but never in `requirements.txt` |
| Event-loop blocking | Sync `httpx.post` inside async endpoints — up to 60 s freeze |
| Training tasks garbage-collected | `create_task` without a strong reference |
| Mock-sniffing in production | Router checked `_is_mock` → replaced with `LOCAL_TRAINING_FALLBACK` setting |
| Hardcoded developer path | `C:\Users\Hamoud KJ\...` shipped to end users |

### Migrations & updater ✅ (`e818608`)
- **Alembic had never run on any installation.** `run_migrations_headless()`
  computed the repo root one directory too low (`parents[2]` vs `parents[3]`),
  found no `alembic.ini`, and returned silently. Every schema came from
  `create_all`; no database had an `alembic_version` row.
- Fixing the path exposed two more faults:
  1. `env.py` calls `asyncio.run()`, which cannot run inside the lifespan loop →
     now runs via `asyncio.to_thread`
  2. **Every FK in the 10-revision chain was `postgresql.UUID`.** On SQLite that
     is NUMERIC affinity while model ids are `CHAR(32)` (TEXT) → `FOREIGN KEY
     constraint failed`. *This is what the `DROP TABLE` hack was working around.*
- Chain squashed to one baseline (`2107bfe05bb2`) using `sa.Uuid()`, which
  renders `CHAR(32)` on SQLite and native `UUID` on Postgres
- `installer.iss` never shipped `alembic.ini` — migrations would have stayed dead
- **Deleted `updater_verify.py`**: it performed no cryptographic verification
  (checked for the substring `"invalid"`). Its minisign key decoded to 18 bytes
  where a real one is 42

### Phase 2 — Honest tests ✅ (`3e59566`)
Rewrote three files that asserted on fixtures rather than the system.
**13 deliberate mutations, all caught.**

| File | Before | After |
|---|---|---|
| `test_network_isolation.py` | 4 tests | **14** — real HTTP, Host-header guard, CORS |
| `test_desktop_packaging.py` | 4 fake | **9** — parses `installer.iss`, catches missing files *and secret leakage* |
| `test_tauri_shell.py` | 4 (one tested a closure defined inside itself) | **9** — parses CSP, demands a 42-byte key |

- Added **real Rust tests** in `sidecar_manager.rs` (3, verified passing)
- `next.config.ts` had `ignoreBuildErrors: true` — production builds ignored
  type errors. Now enforced.

### Phase 4 — Functional correctness ✅ (`a5174b1`, `041ec90`, `26fb9c5`, `492519a`, `7e02e8f`)

**17 defects.** All found by running the app; none visible from the test suite.

1. **Confusion matrix / per-class never worked.** Three filters stripped them —
   declared "✅ Done" in the feature plan. The unit test passed because it used
   a `FakeTrial` the ORM listeners never touch.
2. **Profiling rejected any file with a text ID column** → `TypeError: unsupported
   operand type(s) for -: 'str' and 'str'`. Customer codes, UUIDs, emails — most
   real tabular data was un-uploadable.
3. **Deleting a trained-on project returned 500** — `backref` carries no cascade,
   so the ORM nulled a NOT NULL column. Fixed with `cascade` + `passive_deletes`.
4. **Tests wrote into live user data** — 143 orphaned directories accumulated.
5. **`AIDSE_DATA_DIR` did not move the database** — isolation was an illusion.
6. **MLflow wrote 12 MB of artifacts into the source tree.**
7. **SHAP broken for every tree model** — code written for SHAP's pre-0.45 list
   API; 0.52 returns `(samples, features, classes)`.
8. **One bad algorithm failed the whole experiment** — `SVC() got multiple values
   for keyword argument 'kernel'`. 4 trials discarded; now 10 complete.
9. **Best-trial selection used Optuna's index**, which desyncs after any failure.
10. **Training learned from row identifiers** — `customer_id` was the *second most
    important feature*. Now excluded (conservatively: keeps near-unique floats).
11. **UI styling required the internet** — all three fonts from Google Fonts CDN.
    Offline, every icon rendered as its ligature name ("dashboard", "lock").
    Now vendored (327 KB). Verified: **zero external requests**.
12. **Starting training froze the UI for 20+ seconds.** Celery's redis *result
    backend* retries 20× at 1 s — `connect_timeout` only bounds the broker.
    Now config-driven (`USE_CELERY`, default off). **Measured: 20 s → 0.17 s.**
13. **App lock that locked nothing** — collected a 4-digit PIN, wrote it to
    `localStorage` in cleartext, never read it back. Removed, and a **real lock
    screen** built for the separate master password (which also had no caller).
14. **Notifications page never populated** — `useState([])` with no writer. Now a
    real store; verified end-to-end with a live training run.
15. **3 of 4 dashboard KPIs hardcoded** (`"—"`, `"0 issues"`).
16. **"Needs attention" always visible** with fixed text → now dynamic, absent
    when nothing is wrong.
17. **An evaluation detail page made of fabricated data** — fake model name,
    "94.2%", "0.92", invented category breakdown. Never called the API. Deleted.

Also: light theme was **fully built and unreachable** (`forcedTheme="dark"` +
`ThemeToggle` returning `null`); settings page translated to English; seven
separate false encryption claims corrected across UI, landing page and docs.

---

## 4. Current state

```
Tests:      283 passed, 1 skipped, 0 failed   (~2–4 min)
Rust:       cargo check clean; cargo test 5 passed
TypeScript: clean
Build:      green, 20 routes
Capabilities verified end-to-end: 16 / 16
```

Toolchain installed this session: **Rust 1.98.1** + **MSVC 14.44** + **Windows
SDK 10.0.26100** (~3 GB downloaded, 3.47 GB on disk). `cargo test` works.

**Disk:** ~31 GB free. `dist/` is 1.3 GB and `dist-installer/` 353 MB — both
regenerable build output still sitting in the tree (gitignored, not deleted).

---

## 5. Remaining work

### Phase 3 — Wire up Tauri ← **IN PROGRESS** (commit `a076702`)

Closes the **last critical security gap** and shrinks the installer from
353 MB to ~15 MB. The chain is broken at every link:

| # | Task | State |
|---|---|---|
| 1 | Add `@tauri-apps/api` | ✅ done |
| 2 | Spawn the sidecar from `main.rs` | ✅ `SidecarManager::spawn()` |
| 3 | Random 256-bit token via `--token` | ✅ done |
| 4 | Frontend handshake (`lib/sidecar.ts`) | ✅ awaited inside `request()` |
| 5 | Random free port | ✅ `find_free_loopback_port()` in Rust |
| 6 | Middleware enforcement | ✅ enforced **when a token is set** — see caveat below |
| 7 | **Rebuild the sidecar binary** | ❌ **NOT DONE — do this before any bundle** |
| 8 | Real minisign key | ❌ not done (updater config currently removed) |
| 9 | **`npm run tauri build` end to end** | ❌ never attempted |

**Caveat on #6, important:** enforcement is conditional on a token existing,
and that is a hard limit, not laziness. A plain browser window cannot attach a
custom header, so the **Edge launcher (`Launch-AIDSE.vbs`) — which is still
what ships — cannot supply a token and cannot be protected this way.** Only the
Tauri shell can. `warn_if_unprotected()` logs this at startup.
So the security gap closes **only when the Tauri build replaces the launcher**
(tasks 7 and 9).

**`/health` is deliberately exempt** from token checks so the launcher's
readiness poll keeps working.

**Next concrete steps:**
1. Rebuild the sidecar: `pyinstaller infrastructure/desktop/sidecar.spec`,
   then copy the exe to `src-tauri/binaries/aidse-backend-x86_64-pc-windows-msvc.exe`
2. `cd apps/web && npm run build` (Tauri serves `out/`)
3. `npx tauri build` — **never run yet**; expect first-build issues
4. Launch the bundled app and confirm: sidecar starts, handshake succeeds,
   API calls carry the token, and a request **without** it gets 403
5. `tauri signer generate` → restore the updater block with a real 42-byte key

**⚠️ Item 6 is the actual security fix.** Right now `AIDSE_INTERNAL_TOKEN` is
never set, so `InternalTokenMiddleware` admits every request — and desktop mode
grants an automatic admin session. **Any process running as the user can call
the entire API.** When this lands, replace the test
`test_unconfigured_token_currently_fails_open` (which documents the gap) with
one asserting rejection.

**⚠️ Item 7 is easy to forget.** Building Tauri with the existing binary would
ship a backend containing `DROP TABLE`, broken migrations, the confusion-matrix
bug and the false encryption claims.

Estimate for what remains: 2–3 days.

### Phase 5 — Dependencies & size (2–3 days)
- `requirements.txt` has **no pinned versions** despite claiming "pinned for
  reproducibility" — all `>=`
- Remove server-era deps: `minio`, `celery`, `redis`, `asyncpg`, `passlib`
- Evaluate dropping `mlflow` (large, and only artifact tracking is used)
- PyInstaller `excludes`

### Phase 6 — Organisation & cleanup (2 days)
- Remove `dist/` (1.3 GB), `dist-installer/` (353 MB), `landing-page.rar`, `mlruns/` — **frees ~1.7 GB**
- Delete 6 empty modules: `deployment`, `monitoring`, `comparison`,
  `services/serving`, `packages/ml-core`, `packages/shared-types`
- Delete unused `infrastructure/` (docker, github-actions, empty k8s dirs)
- Remove `create_all` from `lifespan` — it masks migration failures, which is
  exactly how the original drift went unnoticed
- Rewrite `AIDSE_COMPLETE_PROJECT_DOCS.md` (still claims 208 tests, SQLCipher, etc.)

### Known smaller items
- `refresh_token` stored in a JS-readable cookie (dormant — desktop bypasses login)
- ReDoS: user regex has no execution timeout (mitigated by a length cap + off-loop)
- 76 eslint warnings
- Arabic language layer planned — settings was translated to English first so
  i18n can be added properly rather than as scattered strings

---

## 6. Conventions used here

- **Verify by running, not by reading.** Every claim in the commits was executed.
- **Mutation-test new tests.** Break the protection, confirm the test fails,
  revert. If it cannot be reproduced, say so in the test docstring — one test
  was *deleted* for reproducing nothing.
- **Never edit source while a test run is in flight** (it caused a false failure).
- **Don't overclaim in UI copy.** The lock screen states plainly that it does not
  encrypt datasets.
- Commit messages explain *why*, including what was wrong before.

---

## 7. Honest notes / open risks

- **Project-delete cascade** is verified by hand against a real file-backed
  database, but the regression test asserts only the *outcome*. The original
  fault could not be reproduced against the in-memory test database — restored
  to the exact broken configuration, the test still passed. Treat a regression
  there as possible even with a green suite.
- **Rust unit tests** in `sidecar_manager.rs` were verified in isolation (copied
  into a scratch crate) because the full crate needs Tauri deps compiled. Run
  `cargo test` inside `src-tauri/` once Phase 3 builds.
- **`aidse-platform`** (the sibling web project) is untouched and still has no
  git repository — deliberately out of scope.
- Stale `__pycache__` carried over from `aidse-platform` made tracebacks point
  at the wrong repository; cleared, but re-check if paths look wrong again.
