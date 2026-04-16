"""GRBL CNC wrapper for Autoprober v2."""

from __future__ import annotations

import os
import re
import time
from typing import Optional

from .logging import log


STATUS_RE = re.compile(
    r"^<(?P<state>[^|>]+)\|MPos:(?P<x>-?\d+(?:\.\d+)?),(?P<y>-?\d+(?:\.\d+)?),(?P<z>-?\d+(?:\.\d+)?)(?P<rest>.*)>$"
)


class CNCError(Exception):
    pass


def parse_status(line: str) -> dict:
    match = STATUS_RE.match(line.strip())
    if not match:
        raise ValueError(f"not a GRBL status line: {line!r}")
    rest = match.group("rest") or ""
    raw_pn = ""
    for part in rest.split("|"):
        if part.startswith("Pn:"):
            raw_pn = part[3:]
            break
    pins = {pin for pin in raw_pn if pin in {"X", "Y", "Z"}}
    return {
        "state": match.group("state"),
        "mpos": (
            float(match.group("x")),
            float(match.group("y")),
            float(match.group("z")),
        ),
        "raw_pn": raw_pn,
        "pins": pins,
        "raw": line,
    }


class CNC:
    """Small runtime wrapper; transport is isolated here, not in apps."""

    def __init__(self, port: str | None = None, baud: int | None = None, log_source: str = "cnc"):
        self.port = port or os.environ.get("AUTOPROBER_CNC_PORT", "/dev/ttyUSB0")
        self.baud = baud or int(os.environ.get("AUTOPROBER_CNC_BAUD", "115200"))
        self.log_source = log_source
        self._serial = None

    def connect(self) -> None:
        import serial  # transport dependency belongs in this wrapper

        self._serial = serial.Serial(self.port, self.baud, timeout=2)
        time.sleep(2)
        self._serial.reset_input_buffer()
        self._serial.write(b"\r\n\r\n")
        time.sleep(1)
        self._serial.reset_input_buffer()
        log(self.log_source, f"connected {self.port} @ {self.baud}")

    def close(self) -> None:
        if self._serial:
            self._serial.close()
            self._serial = None

    def _write(self, command: str) -> None:
        if not self._serial:
            raise CNCError("CNC is not connected")
        log(self.log_source, f"-> {command}")
        self._serial.write((command + "\n").encode("ascii"))

    def unlock(self) -> None:
        self._write("$X")
        time.sleep(0.2)

    def home(self) -> None:
        self._write("$H")

    def feed_hold(self) -> None:
        if not self._serial:
            raise CNCError("CNC is not connected")
        log(self.log_source, "-> ! feed hold")
        self._serial.write(b"!")

    def get_status(self) -> dict:
        if not self._serial:
            raise CNCError("CNC is not connected")
        self._serial.write(b"?")
        deadline = time.time() + 2
        while time.time() < deadline:
            line = self._serial.readline().decode("ascii", errors="replace").strip()
            if line.startswith("<") and line.endswith(">"):
                status = parse_status(line)
                log(self.log_source, f"<- {line}")
                return status
        raise CNCError("timed out waiting for GRBL status")

    def read_settings(self) -> dict:
        if not self._serial:
            raise CNCError("CNC is not connected")
        settings = {}
        self._write("$$")
        deadline = time.time() + 10
        while time.time() < deadline:
            line = self._serial.readline().decode("ascii", errors="replace").strip()
            if not line:
                continue
            log(self.log_source, f"<- {line}")
            if line == "ok":
                return settings
            match = re.match(r"^\$(\d+)=(.+)$", line)
            if match:
                settings[match.group(1)] = match.group(2)
        raise CNCError("timed out waiting for GRBL settings")

    def wait_for_idle(self, timeout: float = 60, poll_interval: float = 0.2) -> dict:
        deadline = time.time() + timeout
        last_status = None
        while time.time() < deadline:
            last_status = self.get_status()
            if last_status["state"] == "Idle":
                return last_status
            time.sleep(poll_interval)
        raise CNCError(f"timed out waiting for idle; last status={last_status}")

    def move_absolute(
        self,
        x: Optional[float] = None,
        y: Optional[float] = None,
        z: Optional[float] = None,
        feed: int = 800,
    ) -> None:
        parts = ["G90", "G1"]
        if x is not None:
            parts.append(f"X{x:.3f}")
        if y is not None:
            parts.append(f"Y{y:.3f}")
        if z is not None:
            parts.append(f"Z{z:.3f}")
        parts.append(f"F{feed}")
        self._write(" ".join(parts))

    def move_relative(
        self,
        dx: float = 0,
        dy: float = 0,
        dz: float = 0,
        feed: int = 800,
    ) -> None:
        parts = ["G91", "G1"]
        if dx:
            parts.append(f"X{dx:.3f}")
        if dy:
            parts.append(f"Y{dy:.3f}")
        if dz:
            parts.append(f"Z{dz:.3f}")
        parts.append(f"F{feed}")
        self._write(" ".join(parts))
