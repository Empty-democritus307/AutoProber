#!/usr/bin/env python3
"""Calibrate microscope field of view with monitored CNC moves."""

from __future__ import annotations

import json
import time
from pathlib import Path

import cv2

from autoprober.calibration import save_calibration
from autoprober.cnc import CNC
from autoprober.logging import log, section
from autoprober.microscope import Microscope
from autoprober.paths import RUNTIME_ROOT
from autoprober.scope import Scope
from autoprober.safety import (
    EndstopMonitor,
    EndstopState,
    classify_endstop_voltage,
    describe_endstop_state,
)


MIN_MATCH_SCORE = 0.70
MIN_VARIANCE = 15.0
MOVE_MM = 2.0


def image_variance(img) -> float:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return float(gray.std())


def template_shift(base, moved):
    gray_base = cv2.cvtColor(base, cv2.COLOR_BGR2GRAY)
    gray_moved = cv2.cvtColor(moved, cv2.COLOR_BGR2GRAY)
    height, width = gray_base.shape
    template_height, template_width = 400, 600
    if height < template_height or width < template_width:
        return 0, 0, 0.0
    x0 = (width - template_width) // 2
    y0 = (height - template_height) // 2
    template = gray_base[y0 : y0 + template_height, x0 : x0 + template_width]
    result = cv2.matchTemplate(gray_moved, template, cv2.TM_CCOEFF_NORMED)
    _, score, _, loc = cv2.minMaxLoc(result)
    return loc[0] - x0, loc[1] - y0, float(score)


def capture_image(microscope: Microscope, path: Path):
    microscope.capture(str(path))
    image = cv2.imread(str(path))
    if image is None:
        raise RuntimeError(f"could not read captured image: {path}")
    return image


def monitored_move(cnc: CNC, monitor: EndstopMonitor, **kwargs) -> None:
    monitor.require_clear()
    cnc.move_relative(**kwargs)
    time.sleep(0.1)
    cnc.wait_for_idle(timeout=30)
    monitor.require_clear()


def main() -> int:
    section("calibrate", "FOV CALIBRATION")
    microscope = Microscope()
    scope = Scope(quiet=True)
    cnc = CNC()
    monitor = None
    runtime_dir = RUNTIME_ROOT

    try:
        microscope.ensure_streamer_running()
        scope.connect()
        voltage = scope.measure_mean(4)
        state = classify_endstop_voltage(voltage)
        if state != EndstopState.CLEAR:
            raise RuntimeError(f"Channel 4 not clear: {describe_endstop_state(voltage)}")

        cnc.connect()
        start_status = cnc.get_status()
        if start_status["state"] != "Idle":
            raise RuntimeError(f"CNC must be Idle before calibration: {start_status['raw']}")
        if start_status.get("pins"):
            raise RuntimeError(f"real limit pins active before calibration: {sorted(start_status['pins'])}")
        start_pos = start_status["mpos"]
        log("calibrate", f"start position: {start_pos}")

        monitor = EndstopMonitor(scope, poll_interval=0.1, hold_callback=cnc.feed_hold)
        monitor.start()

        base_path = runtime_dir / "calib_c0.jpg"
        x_path = runtime_dir / "calib_cx.jpg"
        y_path = runtime_dir / "calib_cy.jpg"

        base = capture_image(microscope, base_path)
        variance = image_variance(base)
        log("calibrate", f"baseline variance: {variance:.1f}")
        if variance < MIN_VARIANCE:
            raise RuntimeError(
                f"image too featureless for calibration: variance {variance:.1f} < {MIN_VARIANCE}"
            )

        log("calibrate", f"X calibration: move +{MOVE_MM:g}mm")
        monitored_move(cnc, monitor, dx=MOVE_MM, feed=500)
        moved_x = capture_image(microscope, x_path)
        monitored_move(cnc, monitor, dx=-MOVE_MM, feed=500)
        dx_px, dy_px, score_x = template_shift(base, moved_x)
        log("calibrate", f"X move: dx_px={dx_px} dy_px={dy_px} score={score_x:.3f}")
        if score_x < MIN_MATCH_SCORE:
            raise RuntimeError(f"X match score too low: {score_x:.3f}")

        log("calibrate", f"Y calibration: move +{MOVE_MM:g}mm")
        monitored_move(cnc, monitor, dy=MOVE_MM, feed=500)
        moved_y = capture_image(microscope, y_path)
        monitored_move(cnc, monitor, dy=-MOVE_MM, feed=500)
        dx_y, dy_y, score_y = template_shift(base, moved_y)
        log("calibrate", f"Y move: dx_px={dx_y} dy_px={dy_y} score={score_y:.3f}")
        if score_y < MIN_MATCH_SCORE:
            raise RuntimeError(f"Y match score too low: {score_y:.3f}")

        height, width = base.shape[:2]
        if abs(dx_px) < 5:
            raise RuntimeError(f"X image shift too small: {dx_px}px")
        if abs(dy_y) < 5:
            raise RuntimeError(f"Y image shift too small: {dy_y}px")

        mm_per_px_x = MOVE_MM / abs(dx_px)
        mm_per_px_y = MOVE_MM / abs(dy_y)
        calibration = {
            "timestamp": time.time(),
            "iso_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "tile_width_px": width,
            "tile_height_px": height,
            "mm_per_px_x": mm_per_px_x,
            "mm_per_px_y": mm_per_px_y,
            "fov_x_mm": width * mm_per_px_x,
            "fov_y_mm": height * mm_per_px_y,
            "x_sign": -1 if dx_px < 0 else 1,
            "y_sign": -1 if dy_y < 0 else 1,
            "z_at_calibration": start_pos[2],
            "position_at_calibration": {
                "x": start_pos[0],
                "y": start_pos[1],
                "z": start_pos[2],
            },
            "match_score_x": score_x,
            "match_score_y": score_y,
            "baseline_variance": variance,
            "move_mm": MOVE_MM,
            "source_images": {
                "base": str(base_path),
                "x": str(x_path),
                "y": str(y_path),
            },
        }
        save_calibration(calibration)
        log("calibrate", f"FOV: {calibration['fov_x_mm']:.2f} x {calibration['fov_y_mm']:.2f} mm")
        log("calibrate", f"saved calibration.json")
        print(json.dumps(calibration, indent=2))
        return 0
    except Exception as exc:
        log("calibrate", f"ERROR: {exc}")
        print(f"ERROR: {exc}")
        return 1
    finally:
        if monitor:
            monitor.stop()
        cnc.close()
        scope.close()


if __name__ == "__main__":
    raise SystemExit(main())
