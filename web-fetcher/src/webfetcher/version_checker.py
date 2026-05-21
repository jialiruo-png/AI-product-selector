#!/usr/bin/env python3
"""Local version helpers for the embedded web fetcher.

The original upstream update checker has been disabled because this project
vendors the fetcher as an internal module.
"""
from __future__ import annotations

from pathlib import Path
from typing import Tuple


def get_current_version() -> str:
    try:
        pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
        if pyproject_path.exists():
            for line in pyproject_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("version = "):
                    return line.split("=", 1)[1].strip().strip('"')
    except Exception:
        pass
    return "0.1.0"


def parse_version(version_str: str) -> Tuple[int, int, int]:
    parts = version_str.lstrip("v").split(".")
    major = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else 0
    minor = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    patch = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    return major, minor, patch


def is_newer_version(current: str, latest: str) -> bool:
    return parse_version(latest) > parse_version(current)


def check_for_updates_async() -> None:
    return None


def check_for_updates() -> None:
    return None
