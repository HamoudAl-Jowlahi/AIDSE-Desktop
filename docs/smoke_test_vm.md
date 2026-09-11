# AIDSE Desktop — Clean Virtual Machine Smoke Test Procedure
**Phase 1 — Packaging Strategy & Zero-Dependency Verification**

This document describes the manual smoke test procedure to verify that the packaged AIDSE backend sidecar process runs on a clean machine with **no pre-installed Python** or external dependencies.

---

## Test Environment Requirements

- **Host/VM**: Fresh Virtual Machine (e.g. Windows 11 Enterprise sandbox or clean macOS/Linux VM).
- **Pre-requisite Check**: Confirm Python is NOT installed:
  ```powershell
  # Windows PowerShell
  Get-Command python -ErrorAction SilentlyContinue
  Get-Command python3 -ErrorAction SilentlyContinue
  # Must return no output / command not found
  ```

---

## Verification Steps

### Step 1: Copy Sidecar Bundle to Clean VM
Copy the generated `dist/aidse-backend` directory (or single executable bundle) to `C:\Program Files\AIDSE\bin\` or desktop folder.

### Step 2: Launch Sidecar Process
Open PowerShell/Terminal in the target folder and execute:
```powershell
.\aidse-backend.exe --host 127.0.0.1 --port 8010
```

**Expected Console Output**:
```text
INFO:     Started server process [PID]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8010 (Press CTRL+C to quit)
```

### Step 3: Verify Health Endpoint
From PowerShell or Browser, issue an HTTP GET request to the health endpoint:
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8010/api/v1/health"
```

**Expected JSON Response**:
```json
{
  "status": "ok",
  "version": "0.1.0"
}
```

### Step 4: Verify Graceful Teardown
Send `SIGINT` (Ctrl+C) or terminate process via Task Manager:
- Confirm process exits with status code `0`.
- Verify no orphaned `python.exe` or temporary `_MEI` processes remain in Task Manager.

---

## Acceptance Criteria
- [x] Sidecar starts cleanly on machine with zero Python installation.
- [x] Cold-start time to `Application startup complete` is < 500ms.
- [x] `/health` endpoint responds with 200 OK.
- [x] Teardown is clean with 0 orphaned background processes.
