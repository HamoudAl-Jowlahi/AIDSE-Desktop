"""
AIDSE Platform — Sidecar Entrypoint for Desktop Runtime
Section 1: Desktop Shell Integration

This script acts as the standalone entry point when AIDSE is bundled as a
Tauri sidecar executable (PyInstaller onedir / embedded Python runtime).

It reads environment options (host, port, internal token), sets up signal handlers
for graceful shutdown, and programmatically launches Uvicorn serving FastAPI.
"""
from __future__ import annotations

import argparse
import os
import sys
import io
if sys.stderr is None:
    sys.stderr = io.StringIO()
if sys.stdout is None:
    sys.stdout = io.StringIO()
if sys.stdin is None:
    sys.stdin = io.StringIO()
import signal
import socket

# Configure environment variables BEFORE any heavy ML imports
_local_app_data = os.getenv("LOCALAPPDATA") or os.path.expanduser("~")
_aidse_dir = os.path.join(_local_app_data, "AIDSE-Desktop")
_mpl_dir = os.path.join(_aidse_dir, "cache", "matplotlib")
try:
    os.makedirs(_mpl_dir, exist_ok=True)
except Exception:
    pass
os.environ["MPLCONFIGDIR"] = _mpl_dir
os.environ["MATPLOTLIBRC"] = _mpl_dir
os.environ["MLFLOW_DISABLE_AGENT_HINT"] = "1"
os.environ["MLFLOW_LOG_UV_FILES"] = "false"
os.environ["PYTHONWARNINGS"] = "ignore"

try:
    import matplotlib
    matplotlib.use("Agg", force=True)
except Exception:
    pass

import uvicorn

# Ensure repository root is in sys.path for local executions
_here = os.path.abspath(__file__)
_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(_here)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

if getattr(sys, "frozen", False):
    exe_dir = os.path.dirname(sys.executable)
    for _cand in [
        os.path.join(exe_dir, "_internal"),
        os.path.dirname(os.path.dirname(exe_dir)),
        exe_dir,
    ]:
        if os.path.isdir(os.path.join(_cand, "apps")):
            if _cand not in sys.path:
                sys.path.insert(0, _cand)


def find_available_port(host: str = "127.0.0.1", preferred_port: int = 8010, max_attempts: int = 50) -> int:
    """Finds an available port starting from preferred_port."""
    for p in range(preferred_port, preferred_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, p))
                return p
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1]


def parse_args(args_list: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIDSE FastAPI Sidecar Process")
    parser.add_argument("--host", type=str, default=os.getenv("APP_HOST", "127.0.0.1"))
    # Default None so an explicitly requested port can be told apart from the
    # fallback. The Tauri shell always passes one it has already reserved.
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--token", type=str, default=os.getenv("AIDSE_INTERNAL_TOKEN", ""))
    return parser.parse_args(args_list)


def main(args_list: list[str] | None = None) -> None:
    args = parse_args(args_list)

    # If requested port is in use, automatically pick next available port
    if args.port is not None:
        # A port was requested explicitly, which means the caller has already
        # told something else to expect it — the Tauri shell hands the very
        # same number to its window. Quietly moving elsewhere would leave the
        # window talking to a port with nothing behind it, so fail loudly
        # instead.
        target_port = args.port
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.bind((args.host, target_port))
        except OSError as exc:
            raise SystemExit(
                f"Port {target_port} on {args.host} is not available ({exc}). "
                "It was requested explicitly, so refusing to start on a "
                "different one."
            )
    else:
        # No explicit port: pick one, starting from the historical default that
        # Launch-AIDSE reads back out of port.txt.
        target_port = int(os.getenv("APP_PORT", "8010"))
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind((args.host, target_port))
            except OSError:
                target_port = find_available_port(args.host, preferred_port=8010)

    # Pass configuration to environment for Settings and token middleware
    os.environ["APP_HOST"] = args.host
    os.environ["APP_PORT"] = str(target_port)
    os.environ["AIDSE_DESKTOP_MODE"] = "1"
    if args.token:
        os.environ["AIDSE_INTERNAL_TOKEN"] = args.token

    local_app_data = os.getenv("LOCALAPPDATA") or os.path.expanduser("~")
    aidse_dir = os.path.join(local_app_data, "AIDSE-Desktop")
    os.makedirs(aidse_dir, exist_ok=True)

    # Write runtime port to port.txt for the desktop launcher
    try:
        with open(os.path.join(aidse_dir, "port.txt"), "w", encoding="utf-8") as pf:
            pf.write(str(target_port))
    except Exception:
        pass

    # Default to a local SQLite database in desktop mode if DATABASE_URL is unset.
    #
    # This must go through get_aidse_data_dir() rather than reading LOCALAPPDATA
    # directly. It used to do the latter, which meant AIDSE_DATA_DIR moved the
    # storage directory and the MLflow database but silently left the main
    # database in the default location — so pointing the app at a scratch
    # directory still wrote projects and datasets into the user's real data.
    if not os.getenv("DATABASE_URL"):
        from apps.api.core.storage import get_aidse_data_dir

        db_file = str((get_aidse_data_dir() / "aidse.db").resolve()).replace("\\", "/")
        os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_file}"

    # Signal handlers for graceful shutdown
    def handle_shutdown(signum, frame):
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handle_shutdown)

    # Import app factory dynamically to avoid import side-effects before sys.path configuration
    from apps.api.main import create_app

    app_instance = create_app()

    config = uvicorn.Config(
        app=app_instance,
        host=args.host,
        port=target_port,
        log_level="info",
        access_log=False,
    )
    server = uvicorn.Server(config)
    server.run()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        import traceback
        local_app_data = os.getenv("LOCALAPPDATA") or os.path.expanduser("~")
        aidse_dir = os.path.join(local_app_data, "AIDSE-Desktop")
        os.makedirs(aidse_dir, exist_ok=True)
        err_path = os.path.join(aidse_dir, "startup_error.log")
        marker_path = os.path.join(aidse_dir, "startup_crashed.txt")
        try:
            with open(err_path, "w", encoding="utf-8") as f:
                traceback.print_exc(file=f)
            with open(marker_path, "w", encoding="utf-8") as f:
                f.write(str(exc))
        except Exception:
            pass
        sys.exit(1)
