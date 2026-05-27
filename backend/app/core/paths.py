from __future__ import annotations

import os
import sys
from pathlib import Path

_APPDATA_DIRNAME = "AveraDesk"
_DATA_DIR_ENV = "AVERA_DESK_DATA_DIR"
_RUNTIME_ENV = "AVERA_DESK_RUNTIME"


def get_backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def is_packaged_runtime() -> bool:
    runtime = os.getenv(_RUNTIME_ENV, "").strip().lower()
    if runtime in {"packaged", "production", "prod"}:
        return True
    return bool(getattr(sys, "frozen", False))


def get_data_root() -> Path:
    configured = os.getenv(_DATA_DIR_ENV, "").strip()
    if configured:
        root = Path(configured).expanduser()
    elif is_packaged_runtime():
        appdata = os.getenv("APPDATA", "").strip()
        if appdata:
            root = Path(appdata) / _APPDATA_DIRNAME
        else:
            root = Path.home() / ".averadesk"
    else:
        root = get_backend_root()

    root.mkdir(parents=True, exist_ok=True)
    return root


def get_logs_dir() -> Path:
    logs_dir = get_data_root() / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def get_db_path() -> Path:
    return get_data_root() / "avera.db"
