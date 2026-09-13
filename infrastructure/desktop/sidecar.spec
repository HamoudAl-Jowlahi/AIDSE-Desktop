# -*- mode: python ; coding: utf-8 -*-

"""
AIDSE Platform — PyInstaller Sidecar Spec File
Phase 1: Packaging Strategy (Tauri Sidecar Process)

Bundles the FastAPI backend, SQLAlchemy, Alembic, Optuna, Scikit-Learn,
XGBoost, LightGBM, CatBoost, and SHAP into a standalone sidecar executable directory (onedir).
"""

import sys
import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files, collect_dynamic_libs

block_cipher = None

# Hidden imports to ensure runtime dependencies (dynamic imports, C extensions) are bundled
hiddenimports = [
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.http.h11_impl',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'sqlalchemy.dialects.sqlite',
    'sqlalchemy.dialects.sqlite.aiosqlite',
    'aiosqlite',
    'alembic',
    'alembic.runtime.migration',
    'pydantic',
    'pydantic_settings',
    'sklearn',
    'sklearn.ensemble',
    'sklearn.linear_model',
    'xgboost',
    'lightgbm',
    'catboost',
    'optuna',
    'shap',
    'mlflow',
    'mlflow.sklearn',
    # vault.py imports keyring inside a try/except, so PyInstaller cannot see
    # it by static analysis. Without these the packaged app silently falls back
    # to the file-based secret instead of Windows Credential Manager.
    'keyring',
    'keyring.backends',
    'keyring.backends.Windows',
    'keyring.backends.fail',
    'win32ctypes.core',
    'win32ctypes.core.cffi',
] + collect_submodules('apps.api') + collect_submodules('services') + collect_submodules('keyring')

datas = [
    # The migration scripts and the alembic.ini the runner resolves from the
    # bundle root. Previously this pointed at apps/api/alembic/, an orphaned
    # second tree that has been removed.
    ('../../apps/api/db/migrations', 'apps/api/db/migrations'),
    ('../../alembic.ini', '.'),
] + collect_data_files('shap') + collect_data_files('xgboost') + collect_data_files('lightgbm') + collect_data_files('optuna')

binaries = collect_dynamic_libs('xgboost') + collect_dynamic_libs('lightgbm')

a = Analysis(
    ['../../apps/api/sidecar_entry.py'],
    pathex=['../..'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    excludes=[
        'tkinter',
        'matplotlib.tests',
        'torch',
        'torchvision',
        'torchaudio',
        'cv2',
        'transformers',
        'nltk',
    ],
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='aidse-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='aidse-backend',
)
