"""USB microscope wrapper for v2."""

from __future__ import annotations

from pathlib import Path
import os
import subprocess
import urllib.request

from .logging import log


class Microscope:
    def __init__(self, snapshot_url: str | None = None):
        self.snapshot_url = snapshot_url or os.environ.get(
            "AUTOPROBER_MICROSCOPE_SNAPSHOT_URL",
            "http://127.0.0.1:8080/?action=snapshot",
        )

    def ensure_streamer_running(self) -> None:
        if subprocess.run(["pgrep", "-x", "mjpg_streamer"], capture_output=True).returncode == 0:
            return
        subprocess.Popen(
            [
                "sudo",
                "mjpg_streamer",
                "-i",
                f"input_uvc.so -d {os.environ.get('AUTOPROBER_MICROSCOPE_DEV', '/dev/video0')} -r 1600x1200 -f 15",
                "-o",
                "output_http.so -p 8080 -w /usr/local/share/mjpg-streamer/www",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        log("microscope", "started mjpg-streamer")

    def capture(self, out_path: str) -> bool:
        path = Path(out_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(self.snapshot_url, timeout=5) as response:
            data = response.read()
        path.write_bytes(data)
        return path.stat().st_size > 1024
