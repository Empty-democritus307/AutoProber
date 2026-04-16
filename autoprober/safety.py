"""Safety primitives for Autoprober v2.

The optical endstop is read from oscilloscope Channel 4. Values below 1.0 V
mean the endstop is triggered. Values from 1.0 V to 4.5 V are not "safe
enough"; they indicate ambiguous wiring or sensor failure and enter STOP.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import threading
import time
from typing import Callable, Optional

from .logging import log


class EndstopState(str, Enum):
    CLEAR = "clear"
    TRIGGERED = "triggered"
    FAULT = "fault"


def classify_endstop_voltage(voltage: Optional[float]) -> EndstopState:
    if voltage is None:
        return EndstopState.FAULT
    if voltage < 1.0:
        return EndstopState.TRIGGERED
    if voltage < 4.5:
        return EndstopState.FAULT
    return EndstopState.CLEAR


def describe_endstop_state(voltage: Optional[float]) -> str:
    state = classify_endstop_voltage(voltage)
    if state == EndstopState.CLEAR:
        return f"clear ({voltage:.2f}V)"
    if state == EndstopState.TRIGGERED:
        return f"triggered ({voltage:.2f}V)"
    if voltage is None:
        return "fault: Channel 4 disabled or unreadable"
    return f"fault: ambiguous Channel 4 voltage ({voltage:.2f}V)"


@dataclass(frozen=True)
class SafetySnapshot:
    state: EndstopState
    voltage: Optional[float]
    reason: str


class EndstopMonitor:
    """Poll scope Channel 4 in a background thread and enter STOP on danger."""

    def __init__(
        self,
        scope,
        channel: int = 4,
        poll_interval: float = 0.1,
        hold_callback: Optional[Callable[[], None]] = None,
        log_source: str = "endstop-mon",
    ):
        self.scope = scope
        self.channel = channel
        self.poll_interval = poll_interval
        self.hold_callback = hold_callback
        self.log_source = log_source

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._hold_sent = False

        self.triggered = False
        self.last_voltage: Optional[float] = None
        self.stop_state = EndstopState.CLEAR
        self.stop_reason = "clear"

    def start(self) -> None:
        self._stop_event.clear()
        self._hold_sent = False
        self.triggered = False
        self.stop_state = EndstopState.CLEAR
        self.stop_reason = "clear"
        self._thread = threading.Thread(target=self._loop, name="endstop-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def snapshot(self) -> SafetySnapshot:
        return SafetySnapshot(self.stop_state, self.last_voltage, self.stop_reason)

    def require_clear(self) -> None:
        if self.triggered:
            raise RuntimeError(self.stop_reason)

    def _enter_stop(self, state: EndstopState, voltage: Optional[float]) -> None:
        self.triggered = True
        self.stop_state = state
        self.stop_reason = describe_endstop_state(voltage)
        log(self.log_source, f"STOP: {self.stop_reason}")
        if self.hold_callback and not self._hold_sent:
            self._hold_sent = True
            try:
                self.hold_callback()
            except Exception as exc:  # pragma: no cover - defensive logging
                log(self.log_source, f"feed_hold callback failed: {exc}")

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                voltage = self.scope.measure_mean(self.channel)
            except Exception as exc:
                log(self.log_source, f"scope read error: {exc}")
                voltage = None
            self.last_voltage = voltage
            state = classify_endstop_voltage(voltage)
            if state != EndstopState.CLEAR:
                self._enter_stop(state, voltage)
                return
            time.sleep(self.poll_interval)
