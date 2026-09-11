"""
AIDSE Platform — Desktop System Settings & Diagnostics Module
Provides hardware metrics, storage management, explorer shortcuts,
and desktop application preferences for offline local use.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import ctypes
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from apps.api.core.dependencies import get_current_user
from apps.api.core.storage import get_aidse_data_dir, get_storage_root
from apps.api.modules.auth.schemas import UserOut

router = APIRouter(prefix="/system", tags=["System Diagnostics & Settings"])


class DesktopSettingsPayload(BaseModel):
    max_training_threads: int = Field(default=4, ge=1, le=64)
    performance_mode: str = Field(default="balanced")  # "balanced" | "max"
    theme: str = Field(default="dark")  # "dark" | "light" | "system"
    require_app_lock: bool = Field(default=False)
    auto_cleanup_cache: bool = Field(default=False)
    launch_on_startup: bool = Field(default=False)


def _get_settings_file() -> Path:
    return get_aidse_data_dir() / "settings.json"


def _read_desktop_settings() -> dict[str, Any]:
    s_file = _get_settings_file()
    cpu_max = os.cpu_count() or 4
    default_threads = max(1, min(4, cpu_max - 1 if cpu_max > 2 else cpu_max))
    defaults = {
        "max_training_threads": default_threads,
        "performance_mode": "balanced",
        "theme": "dark",
        "require_app_lock": False,
        "auto_cleanup_cache": False,
        "launch_on_startup": False,
    }
    if s_file.is_file():
        try:
            with open(s_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                defaults.update(data)
        except Exception:
            pass
    return defaults


def _get_dir_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    try:
        for entry in path.rglob("*"):
            if entry.is_file():
                try:
                    total += entry.stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


@router.get("/info", summary="Get system specifications, hardware & storage stats")
async def get_system_info(current_user: UserOut = Depends(get_current_user)) -> dict[str, Any]:
    data_dir = get_aidse_data_dir()
    storage_dir = get_storage_root()

    # Disk usage
    try:
        disk = shutil.disk_usage(str(storage_dir))
        disk_total_gb = round(disk.total / (1024**3), 2)
        disk_free_gb = round(disk.free / (1024**3), 2)
        disk_used_percent = round(((disk.total - disk.free) / disk.total) * 100, 1)
    except Exception:
        disk_total_gb = 0.0
        disk_free_gb = 0.0
        disk_used_percent = 0.0

    # Hardware Memory (RAM)
    total_ram_gb = 0.0
    avail_ram_gb = 0.0
    if sys.platform == "win32":
        try:
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            total_ram_gb = round(stat.ullTotalPhys / (1024**3), 2)
            avail_ram_gb = round(stat.ullAvailPhys / (1024**3), 2)
        except Exception:
            pass

    # Storage Breakdown
    datasets_dir = storage_dir / "datasets"
    models_dir = storage_dir / "models"
    cache_dir = storage_dir / "cache"
    db_file = data_dir / "aidse.db"

    datasets_size = _get_dir_size(datasets_dir)
    models_size = _get_dir_size(models_dir)
    cache_size = _get_dir_size(cache_dir)
    db_size = db_file.stat().st_size if db_file.is_file() else 0

    # ML packages info
    import importlib.metadata
    ml_packages = {}
    for pkg in ["scikit-learn", "xgboost", "lightgbm", "catboost", "optuna", "shap"]:
        try:
            ml_packages[pkg] = importlib.metadata.version(pkg)
        except Exception:
            ml_packages[pkg] = "Available"

    return {
        "app_name": "AIDSE Desktop",
        "app_version": "0.1.0",
        "edition": "Standalone Desktop (Offline AI Engine)",
        "backend_port": int(os.getenv("APP_PORT", "8010")),
        "environment": {
            "os": f"{platform.system()} {platform.release()}",
            "arch": platform.machine(),
            "python_version": platform.python_version(),
        },
        "hardware": {
            "cpu_cores": os.cpu_count() or 1,
            "total_ram_gb": total_ram_gb,
            "available_ram_gb": avail_ram_gb,
        },
        "storage": {
            "data_dir": str(data_dir),
            "storage_dir": str(storage_dir),
            "disk_total_gb": disk_total_gb,
            "disk_free_gb": disk_free_gb,
            "disk_used_percent": disk_used_percent,
            "db_size_mb": round(db_size / (1024**2), 2),
            "datasets_size_mb": round(datasets_size / (1024**2), 2),
            "models_size_mb": round(models_size / (1024**2), 2),
            "cache_size_mb": round(cache_size / (1024**2), 2),
            "total_storage_used_mb": round((db_size + datasets_size + models_size + cache_size) / (1024**2), 2),
        },
        "ml_libraries": ml_packages,
    }


def _set_startup_registry(enable: bool) -> None:
    if sys.platform != "win32":
        return
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "AIDSE-Desktop"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            if enable:
                exe_resolved = Path(sys.executable).resolve()
                candidates = [
                    exe_resolved.parents[2] / "Launch-AIDSE.vbs",
                    exe_resolved.parents[1] / "Launch-AIDSE.vbs",
                    exe_resolved.parent / "Launch-AIDSE.vbs",
                    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "AIDSE Desktop" / "Launch-AIDSE.vbs",
                    Path(r"C:\Users\Hamoud KJ\Desktop\AI Projects  Researches\AIDSE Project\aidse-desktop\Launch-AIDSE.vbs"),
                ]
                launcher_vbs = None
                for cand in candidates:
                    if cand.is_file():
                        launcher_vbs = cand
                        break

                wscript_exe = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "wscript.exe"
                wscript_str = f'"{wscript_exe}"' if wscript_exe.is_file() else "wscript.exe"

                if launcher_vbs:
                    cmd = f'{wscript_str} "{launcher_vbs}"'
                else:
                    cmd = f'"{exe_resolved}"'
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                except FileNotFoundError:
                    pass
    except Exception:
        pass


@router.get("/settings", summary="Get desktop configuration settings")
async def get_settings(current_user: UserOut = Depends(get_current_user)) -> dict[str, Any]:
    return _read_desktop_settings()


@router.post("/settings", summary="Update desktop configuration settings")
async def update_settings(payload: DesktopSettingsPayload, current_user: UserOut = Depends(get_current_user)) -> dict[str, Any]:
    s_file = _get_settings_file()
    settings_data = payload.model_dump()
    try:
        with open(s_file, "w", encoding="utf-8") as f:
            json.dump(settings_data, f, indent=2)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save settings: {exc}")

    # Synchronize real Windows Startup behavior
    if "launch_on_startup" in settings_data:
        _set_startup_registry(bool(settings_data["launch_on_startup"]))

    return {"status": "ok", "settings": settings_data}



@router.post("/open-storage", summary="Open the local storage folder in Windows Explorer")
async def open_storage_folder(current_user: UserOut = Depends(get_current_user)) -> dict[str, Any]:
    storage_dir = get_storage_root()
    try:
        if sys.platform == "win32":
            os.startfile(str(storage_dir))
        else:
            subprocess.Popen(["xdg-open", str(storage_dir)])
        return {"status": "ok", "path": str(storage_dir)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to open storage directory: {exc}")


@router.post("/clear-cache", summary="Clear temporary cache files and scratch buffers")
async def clear_cache(current_user: UserOut = Depends(get_current_user)) -> dict[str, Any]:
    storage_dir = get_storage_root()
    cache_dirs = [storage_dir / "cache", storage_dir / "temp"]
    freed_bytes = 0
    for c_dir in cache_dirs:
        if c_dir.exists():
            freed_bytes += _get_dir_size(c_dir)
            try:
                shutil.rmtree(c_dir, ignore_errors=True)
                c_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
    return {
        "status": "ok",
        "freed_bytes": freed_bytes,
        "freed_mb": round(freed_bytes / (1024**2), 2),
        "message": f"Cache cleaned successfully (freed {round(freed_bytes / (1024**2), 2)} MB)",
    }