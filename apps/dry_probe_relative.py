#!/usr/bin/env python3
"""Relative dry-probe move from a verified visual anchor.

This helper is only for cases where the current microscope frame has already
been matched to a recorded XYZ anchor. It does not trust GRBL's current MPos.
"""

from __future__ import annotations

import argparse
import math
import sys
import time

from autoprober.cnc import CNC
from autoprober.logging import log, section
from autoprober.safety import EndstopMonitor, EndstopState, classify_endstop_voltage, describe_endstop_state
from autoprober.scope import Scope


def _require_clear(scope: Scope, context: str) -> float:
    voltage = scope.measure_mean(4)
    state = classify_endstop_voltage(voltage)
    if state != EndstopState.CLEAR:
        raise RuntimeError(f"{context}: STOP {describe_endstop_state(voltage)}")
    return voltage


def _require_no_real_limits(cnc: CNC, context: str) -> dict:
    status = cnc.get_status()
    pins = sorted(status.get("pins") or [])
    if pins:
        raise RuntimeError(f"{context}: real CNC limit pin active: {','.join(pins)}")
    if str(status.get("state", "")).lower().startswith("alarm"):
        raise RuntimeError(f"{context}: CNC alarm: {status.get('raw', status)}")
    return status


def _run_motion(cnc: CNC, scope: Scope, desc: str, *, dx: float = 0, dy: float = 0, dz: float = 0, feed: int) -> None:
    voltage = _require_clear(scope, f"before {desc}")
    status = _require_no_real_limits(cnc, f"before {desc}")
    log("operator", f"{desc}: start dx={dx:.3f} dy={dy:.3f} dz={dz:.3f} feed={feed} c4={voltage:.2f} status={status.get('raw')}")
    monitor = EndstopMonitor(scope, poll_interval=0.1, hold_callback=cnc.feed_hold)
    monitor.start()
    try:
        cnc.move_relative(dx=dx, dy=dy, dz=dz, feed=feed)
        cnc.wait_for_idle(timeout=20, poll_interval=0.1)
        monitor.require_clear()
    finally:
        monitor.stop()
    voltage = _require_clear(scope, f"after {desc}")
    status = _require_no_real_limits(cnc, f"after {desc}")
    log("operator", f"{desc}: complete c4={voltage:.2f} status={status.get('raw')}")


def _chunked_delta(delta: float, max_step: float) -> list[float]:
    if delta == 0:
        return []
    steps = int(math.ceil(abs(delta) / max_step))
    whole = delta / steps
    return [whole for _ in range(steps)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--anchor-x", type=float, required=True)
    parser.add_argument("--anchor-y", type=float, required=True)
    parser.add_argument("--target-x", type=float, required=True)
    parser.add_argument("--target-y", type=float, required=True)
    parser.add_argument("--z-hop", type=float, default=0.5)
    parser.add_argument("--xy-step", type=float, default=5.0)
    parser.add_argument("--xy-feed", type=int, default=500)
    parser.add_argument("--z-feed", type=int, default=120)
    parser.add_argument("--touch-step", type=float, default=0.05)
    parser.add_argument("--max-touch", type=float, default=1.5)
    parser.add_argument("--xy-only", action="store_true")
    args = parser.parse_args()

    section("operator", "DRY PROBE RELATIVE")
    dx = args.target_x - args.anchor_x
    dy = args.target_y - args.anchor_y
    log(
        "operator",
        "dry probe target from verified visual anchor: "
        f"anchor=({args.anchor_x:.3f},{args.anchor_y:.3f}) "
        f"target=({args.target_x:.3f},{args.target_y:.3f}) "
        f"delta=({dx:.3f},{dy:.3f})",
    )

    scope = Scope(quiet=True)
    cnc = CNC()
    try:
        scope.connect()
        cnc.connect()
        _require_clear(scope, "startup")
        _require_no_real_limits(cnc, "startup")

        if args.z_hop:
            _run_motion(cnc, scope, "z hop before XY", dz=abs(args.z_hop), feed=args.z_feed)

        for index, step in enumerate(_chunked_delta(dx, args.xy_step), start=1):
            _run_motion(cnc, scope, f"XY X chunk {index}", dx=step, feed=args.xy_feed)
        for index, step in enumerate(_chunked_delta(dy, args.xy_step), start=1):
            _run_motion(cnc, scope, f"XY Y chunk {index}", dy=step, feed=args.xy_feed)

        if args.z_hop:
            _run_motion(cnc, scope, "return to focus Z after XY", dz=-abs(args.z_hop), feed=args.z_feed)

        if args.xy_only:
            log("operator", "xy-only requested; stopping before touch descent")
            return 0

        descended = 0.0
        touch_step = -abs(args.touch_step)
        while descended < args.max_touch:
            try:
                _run_motion(cnc, scope, f"touch descent {descended + abs(touch_step):.3f}mm", dz=touch_step, feed=args.z_feed)
            except Exception as exc:
                log("operator", f"STOP during touch descent after {descended:.3f}mm: {exc}")
                print(f"STOP: {exc}")
                return 2
            descended += abs(touch_step)
            time.sleep(0.05)
        log("operator", f"no C4 trigger after {descended:.3f}mm descent; stopping")
        print(f"NO_TRIGGER after {descended:.3f}mm descent")
        return 3
    except Exception as exc:
        log("operator", f"dry probe failed: {exc}")
        print(f"ERROR: {exc}")
        return 1
    finally:
        cnc.close()
        scope.close()


if __name__ == "__main__":
    raise SystemExit(main())
