# V2 Operations

## Session Start

1. Run `apps/preflight.py`.
2. Confirm Channel 4 is clear.
3. Run `apps/home.py`.
4. Calibrate over visible features.
5. Proceed only with workflows that keep `EndstopMonitor` active during motion.

## Motion

All motion workflows must create an `EndstopMonitor` before motion starts and stop it after motion has ended. If the monitor enters STOP, the app exits without more motion.
