"""Software kill latch for Autoprober."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import os


KILL_PATH = Path(os.environ.get("AUTOPROBER_KILL_PATH", "~/.local/state/autoprober/autoprober.kill")).expanduser()


def latch_kill(reason: str) -> None:
    KILL_PATH.parent.mkdir(parents=True, exist_ok=True)
    KILL_PATH.write_text(
        f"{datetime.now().isoformat(timespec='seconds')} {reason.strip() or 'kill requested'}\n",
        encoding="utf-8",
    )


def clear_kill() -> None:
    try:
        KILL_PATH.unlink()
    except FileNotFoundError:
        pass


def kill_active() -> bool:
    return KILL_PATH.exists()


def kill_reason() -> str:
    if not KILL_PATH.exists():
        return ""
    return KILL_PATH.read_text(encoding="utf-8", errors="ignore").strip()
