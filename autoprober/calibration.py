"""Calibration helpers."""

from __future__ import annotations

import json

from .paths import CALIBRATION_PATH


def load_calibration(path=CALIBRATION_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def save_calibration(calibration: dict, path=CALIBRATION_PATH) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(calibration, handle, indent=2)
