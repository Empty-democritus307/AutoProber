"""Runtime paths for Autoprober.

Defaults are intentionally generic so this public release does not bake in a
specific lab host or operator account. Override them with environment variables
on the machine that is connected to hardware.
"""

from pathlib import Path
import os


RUNTIME_ROOT = Path(os.environ.get("AUTOPROBER_RUNTIME_ROOT", "~/.local/share/autoprober")).expanduser()
CALIBRATION_PATH = RUNTIME_ROOT / "calibration.json"
FLATFIELD_PATH = RUNTIME_ROOT / "flatfield.jpg"
TARGET_INFO_PATH = RUNTIME_ROOT / "target_info.json"
