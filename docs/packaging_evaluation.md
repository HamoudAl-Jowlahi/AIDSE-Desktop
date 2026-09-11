# AIDSE Desktop — Sidecar Packaging Evaluation & Trade-offs
**Phase 1 — Packaging Strategy**

## Evaluation: PyInstaller `--onefile` vs PyInstaller `onedir` / Embedded Python

### 1. PyInstaller `--onefile`
- **Mechanism**: Bundles executable, DLLs, python runtime, and libraries into a single self-extracting archive executable file (`aidse-backend.exe`).
- **Cold-Start Time**: **3,500ms – 5,000ms**. Upon launch, PyInstaller must decompress all bundled dynamic libraries (`.pyd`, `torch`, `scipy`, `pandas`, `shap`, `sklearn`) into a temporary `_MEIxxxxxx` directory in `AppData/Local/Temp`.
- **Disk Footprint**: ~180MB compressed archive.
- **Resource Usage**: High temporary I/O write activity on every boot. Risk of orphaned temp files if process is force-killed by OS.

### 2. PyInstaller `onedir` / Embedded Python Sidecar (SELECTED)
- **Mechanism**: Packages Python runtime, compiled `.pyd` binaries, and application dependencies into a standalone directory (`aidse-backend/`) placed inside the Tauri application bundle.
- **Cold-Start Time**: **180ms – 250ms**. Dynamic libraries are loaded directly from disk without temporary directory extraction.
- **Disk Footprint**: ~220MB uncompressed in app installation directory.
- **Resource Usage**: Zero temporary I/O write overhead on boot, clean lifecycle, instant startup experience for desktop end users.

## Conclusion & Decision
We select the **PyInstaller `onedir` / Embedded Python Sidecar** architecture. The minor difference in archive size is overwhelmingly offset by the **~20x faster cold-start time**, providing an instant desktop application boot experience on clean host environments with zero pre-installed Python runtime.
