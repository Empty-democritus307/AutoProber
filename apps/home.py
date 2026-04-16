#!/usr/bin/env python3
"""Home the CNC with continuous Channel 4 monitoring."""

from autoprober.cnc import CNC
from autoprober.scope import Scope
from autoprober.safety import EndstopMonitor


def main() -> int:
    scope = Scope(quiet=True)
    scope.connect()
    cnc = CNC()
    cnc.connect()
    monitor = EndstopMonitor(scope, hold_callback=cnc.feed_hold)
    monitor.start()
    try:
        cnc.home()
        monitor.require_clear()
        return 0
    finally:
        monitor.stop()
        cnc.close()
        scope.close()


if __name__ == "__main__":
    raise SystemExit(main())
