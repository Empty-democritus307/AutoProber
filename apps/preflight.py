#!/usr/bin/env python3
"""V2 preflight checks."""

from __future__ import annotations

from autoprober.safety import EndstopState
from autoprober.scope import Scope


def check_endstop() -> tuple[bool, str]:
    with Scope(quiet=True) as scope:
        state, voltage = scope.read_endstop(4)
    if state != EndstopState.CLEAR:
        return False, f"Channel 4 STOP state: {state.value}, voltage={voltage}"
    return True, f"Channel 4 clear: {voltage:.2f}V"


def main() -> int:
    ok, detail = check_endstop()
    print(detail)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
