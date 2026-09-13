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
Tests:      298 passed, 0 skipped, 0 failed   (apps/api, ~2 min)
Rust:       cargo check clean; cargo test 8 passed
TypeScript: clean
Build:      green, 20 routes
Capabilities verified end-to-end: 16 / 16
Installer:  NSIS, 236.5 MB — current, launched and verified
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
| 1 | Add `@tauri-apps/api` | ✅ |
| 2 | Spawn the backend from Rust | ✅ `SidecarManager::spawn()` |
| 3 | Random 256-bit token via `--token` | ✅ |
| 4 | Frontend handshake (`lib/sidecar.ts`) | ✅ awaited inside `request()` |
| 5 | Random free port | ✅ and the sidecar now honours it strictly |
| 6 | Middleware enforcement | ✅ **verified on the packaged exe** |
| 7 | Rebuild the sidecar | ✅ rebuilt, migrations + keyring confirmed inside it |
| 8 | Bundle the backend correctly | ✅ `bundle.resources` (see below) |
| 9 | Root `package.json` + Tauri CLI | ✅ neither existed |
| 10 | `tauri build` produces a working app | ✅ NSIS installer, **235.6 MB** (was 353 MB) |
| 11 | Launch the bundle and confirm the handshake | ✅ **two defects found and fixed** |
| 12 | Real minisign key | ✅ generated by the owner; public half committed |
| 13 | GitHub Releases updater | ✅ live — awaiting the first published release |

**Verified against the packaged executable, not just source:**

```
no token      -> 403      alembic_version = 2107bfe05bb2 (19 tables)
wrong token   -> 403      app secret -> Windows Credential Manager
correct token -> 200      (no file fallback, so the keyring hidden
/health       -> 200       import took effect)
```

**Two structural faults found while packaging:**

1. **`externalBin` could never have worked.** It copies one file; PyInstaller
   emits a directory (60 MB stub + 790 MB `_internal` holding the Python DLL).
   Running the committed stub alone gives `Failed to load Python DLL`. Any
   Tauri bundle built from that config would have shipped a window with no
   backend. Now bundled via `bundle.resources` and launched by path with
   `std::process::Command` — which also means the webview needs no shell
   permission, so `shell:allow-execute` stayed removed.
2. **The Tauri CLI was never installed** and there was no root `package.json`.
   `npx tauri build` failed outright, which means the desktop bundle had not
   been produced on this machine even once.

### Item 11 found two defects the build could not

The bundle had been produced but never run. Running it surfaced both of
these immediately; neither is visible from source alone.

**1. The shell looked for the backend in a directory that does not exist**
(`df0ac40`). It resolved `resource_dir()/backend/aidse-backend/aidse-backend.exe`
while the bundler writes `resource_dir()/backend/aidse-backend.exe`, because
`"../dist/aidse-backend": "backend/"` copies the directory's *contents*. The
installer would have worked, the window would have opened, and every request
would have failed — the shape of failure that looks like the whole app is
broken. Two tests now hold the config and the Rust join chain together.

**2. Closing the window left the backend running** (`d9efc36`). Windows does
not take a child down with its parent and nothing here did either, so every
launch leaked a 390 MB process still holding its port. This is where the eight
resident backends came from. The manager now owns the child and stops it on
`RunEvent::Exit`; the supervisor had to move from a blocking `wait()` to a
polled `try_wait()`, because it held the mutex the child lives behind exactly
when shutdown needs it.

**Verified against the running bundle, not the source:**

```
backend spawned from   target/release/backend/aidse-backend.exe   (parent = shell)
port 62460, token ab4da3eb… (64 hex, fresh per launch)
/health            no token      -> 200
/api/v1/projects   no token      -> 403
/api/v1/projects   wrong token   -> 403
/api/v1/projects   shell's token -> 200
window closed      -> 0 shells, 0 backends, port released
```

---

### Where this session stopped

Phase 3 is complete. The updater is live and the bundle has been launched,
exercised and closed.

**The signing key exists.** Generated by the owner on 2026-09-13; the private
half never entered this repository or a session. Both Actions secrets
(`TAURI_SIGNING_PRIVATE_KEY`, `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`) are set.
`plugins.updater.pubkey` carries the public half, so
`test_updater_public_key_is_a_real_minisign_key` asserts rather than skips.

Losing the private key or its password means no installed copy can ever be
updated again — they all carry this public key and will reject anything else.

**Nothing is published yet**, so
`releases/latest/download/latest.json` returns 404 today. That is the state
every launch meets until the first release, and it is handled: the automatic
check is silent, so a 404 leaves the UI untouched and logs to the console.
Verified by launching the built shell and waiting past the check — alive,
responding, backend up, and no banner.

To publish the first release, follow `docs/releasing.md`: bump the version in
`tauri.conf.json`, `src-tauri/Cargo.toml` and `package.json`, tag it, push,
then press Publish on the draft the workflow opens.

**What is already wired:**

- `src-tauri/Cargo.toml` — `tauri-plugin-updater` (target-gated off mobile)
- `src-tauri/src/main.rs` — plugin registered
- `src-tauri/capabilities/default.json` — `updater:default`
- `src-tauri/tauri.conf.json` — endpoint
  `https://github.com/HamoudAl-Jowlahi/AIDSE-Desktop/releases/latest/download/latest.json`,
  NSIS `installMode: passive`
- `apps/web/lib/updater.ts` — daily throttled check, per-version dismissal,
  download progress, relaunch; failures stay in the console
- `apps/web/components/layout/UpdateBanner.tsx` — corner toast, mounted inside
  the lock so it never renders over a locked workspace
- Settings → Diagnostics — **Check for updates**, reports either outcome
- `.github/workflows/release.yml` — refuses to build when the tag and
  `tauri.conf.json` version disagree; publishes a **draft** release with the
  installer, its `.sig` and `latest.json`
- `docs/releasing.md` — the full procedure

**Git remote added this session:** `origin` →
`https://github.com/HamoudAl-Jowlahi/AIDSE-Desktop.git`. Nothing has been
pushed yet; the branch is `master` while the repo's main branch is `main`.

**Also dropped the MSI target** (`76a4b2a`). It failed with `timeout: global`
fetching `wix314-binaries.zip`, and MSI only matters for group-policy
deployment, which a per-user desktop app does not use.

**Then:** Phase 5 continues. Four dependencies are gone (`1984999`):
`asyncpg`, `minio`, `redis` had no importer anywhere, and `celery`'s only
importer was `services/worker` — a "Phase 0: Scaffold only" package needing a
Redis broker, reached solely through a `USE_CELERY` branch that defaults off
because probing for a broker froze experiment creation for twenty seconds.
Training now has one route: in-process.

**mlflow stays for now**, by the owner's decision. Worth revisiting: 996
submodules in the bundle and 113 MB of `mlruns/` on disk, for 12 calls whose
only user-visible output is an un-clickable run id in the experiments table.

Phases 5 and 6 are done. What changed:

**Phase 5 — dependencies.** Everything is pinned with `==` at the versions the
suite passes on, in `requirements.txt` (runtime) and `requirements-dev.txt`
(tools, including a pinned PyInstaller). The release workflow installs only the
runtime file. Ranges were dangerous here specifically: the app ships as a
PyInstaller bundle compiled from whatever they resolved to, so a release could
have been built against versions nobody ran. `httpx` moved to runtime — four
production modules import it, despite the comment calling it test-only.

**Phase 6 — cleanup.** Deleted: `installer.iss` and `Launch-AIDSE.bat/.vbs`
(the Edge-launcher build), `infrastructure/docker/` (PostgreSQL + Redis +
MinIO + Celery worker), `infrastructure/github-actions/ci.yml` (outside
`.github/workflows`, so GitHub never ran it), `packages/ml-core/` (six empty
files), the `comparison`, `deployment` and `monitoring` api modules (one empty
`__init__.py` each), `uv.lock` (listed no dependencies), `README_DESKTOP.md`,
and 549 MB of stale build output.

`create_all` is out of the lifespan. Verified against a fresh database in a
temp directory: migrations alone produce 19 tables stamped at `2107bfe05bb2`.

`README.md` and `AIDSE_COMPLETE_PROJECT_DOCS.md` are rewritten. The first told
readers to install Docker Desktop; the second claimed Celery support, a forced
dark theme, 208 tests and a 10-15 MB installer. `.env.example` defaulted
`APP_HOST` to `0.0.0.0`, contradicting the loopback-only default in config.

The four tests that parsed `installer.iss` were replaced rather than dropped.
They guarded something real — that the shipped artifact carries `alembic.ini`
and the migrations, and no keys or databases — so the same assertions now read
`sidecar.spec`, plus one that reads the built bundle when present.

### Deleting the launcher closed a hole and opened a bug

Both fixed in `bbe9e70`.

**The hole:** token enforcement was conditional because the `.vbs` opened a
plain browser window, which cannot attach a custom header. An installed copy
started that way ran unprotected and all the code could do was warn.
`sidecar_entry.py` now refuses to start without a token. Dev and tests still
run unprotected — that is why the middleware stays conditional — but the
shipped path cannot end up in that state.

**The bug:** `_set_startup_registry` looked for the `.vbs` and fell back to
`sys.executable`, which inside the bundle is `aidse-backend.exe`. Once the
`.vbs` was gone, enabling "launch on startup" would have written the *backend*
into the Run key: a headless 390 MB process at every login, no window, no
token. It now resolves the shell, and removes the entry if it cannot find one.

### Deliberately left alone

- **`dist/` (848 MB)** — the built backend. Deleting it frees the most space
  but forces a ~20 minute PyInstaller run before the next bundle can be built.
  It is gitignored build output; delete it whenever the space is worth more.
- **`mlruns/` (113 MB)** — eight AutoML runs with real model artifacts.
  Deleting it right after deciding to keep mlflow seemed contradictory, and it
  is data rather than build output. Say the word and it goes.

Disk: 27 GB free.

### The sidecar bundle is now stale

`dist/aidse-backend` predates the `create_all` removal, the token requirement
and the startup-registry fix, because those live in `apps/api` and only reach
the bundle through PyInstaller. Rebuild before cutting a release:

```bash
.venv/Scripts/pyinstaller infrastructure/desktop/sidecar.spec --distpath dist --noconfirm
npm run build
```

The release workflow does this from scratch, so a tagged release is unaffected.

### Uncommitted, and not mine

`package.json`, `src-tauri/Cargo.toml` and `src-tauri/tauri.conf.json` are
bumped 0.1.0 -> 0.2.0 in the working tree. That is step 1 of
`docs/releasing.md` and is left unstaged for the owner to commit and tag.

### Remaining known issues

- The refresh token sits in a cookie readable by JavaScript.
- 76 eslint warnings in the frontend, mostly `any` and unused bindings.
- ReDoS timeout on user-supplied regex in the evaluation scorer.
- Nothing has been pushed: the branch is `master`, the repository's default is
  `main`.
