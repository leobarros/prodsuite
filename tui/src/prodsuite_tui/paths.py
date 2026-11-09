"""Pastas de dados por sistema operacional."""

from __future__ import annotations

import os
import platform
from pathlib import Path


def data_dir() -> Path:
    override = os.environ.get("PRODSUITE_TUI_DATA")
    if override:
        return Path(override).expanduser()
    system = platform.system()
    if system == "Windows":
        root = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
        return Path(root) / "ProdSuiteTUI"
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "ProdSuiteTUI"
    root = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    return Path(root) / "prodsuite-tui"


def database_path() -> Path:
    return data_dir() / "prodsuite.db"


def ensure_data_dir() -> Path:
    path = data_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path
