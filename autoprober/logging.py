"""Shared logging helpers."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import os
import sys


LOG_PATH = Path(os.environ.get("AUTOPROBER_LOG_PATH", "~/.local/state/autoprober/autoprober.log")).expanduser()


def log(source: str, message: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] [{source}] {message}"
    try:
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception:
        print(line, file=sys.stderr)


def section(source: str, title: str) -> None:
    log(source, f"=== {title} ===")


def progress(source: str, current: int, total: int, description: str = "") -> None:
    log(source, f"PROGRESS {current}/{total} {description}".strip())
