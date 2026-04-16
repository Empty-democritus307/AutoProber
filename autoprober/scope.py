"""Siglent scope wrapper for v2."""

from __future__ import annotations

import re
import socket
import os
from typing import Optional

from .logging import log
from .safety import classify_endstop_voltage


MEASURE_RE = re.compile(r",\s*([-+]?\d+(?:\.\d+)?(?:E[-+]?\d+)?)V", re.IGNORECASE)


class Scope:
    def __init__(self, ip: str | None = None, port: int | None = None, timeout: float = 3, quiet: bool = False):
        self.ip = ip or os.environ.get("AUTOPROBER_SCOPE_HOST", "127.0.0.1")
        self.port = port or int(os.environ.get("AUTOPROBER_SCOPE_PORT", "5025"))
        self.timeout = timeout
        self.quiet = quiet
        self._sock = None

    def connect(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(self.timeout)
        self._sock.connect((self.ip, self.port))
        if not self.quiet:
            log("scope", f"connected {self.ip}:{self.port}")

    def close(self) -> None:
        if self._sock:
            self._sock.close()
            self._sock = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def query(self, command: str) -> str:
        if not self._sock:
            raise RuntimeError("scope is not connected")
        if not self.quiet:
            log("scope", f"-> {command}")
        self._sock.sendall((command + "\n").encode("ascii"))
        response = self._sock.recv(4096).decode("ascii", errors="ignore").strip()
        if not self.quiet:
            log("scope", f"<- {response}")
        return response

    def idn(self) -> str:
        return self.query("*IDN?")

    def measure_mean(self, channel: int) -> Optional[float]:
        response = self.query(f"C{channel}:PAVA? MEAN")
        if "****" in response:
            return None
        match = MEASURE_RE.search(response)
        if not match:
            return None
        return float(match.group(1))

    def read_endstop(self, channel: int = 4):
        voltage = self.measure_mean(channel)
        return classify_endstop_voltage(voltage), voltage
