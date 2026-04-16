#!/usr/bin/env python3
"""V2 dashboard server."""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime
import os
import re
import subprocess
import time
from typing import Optional
import urllib.request

try:
    from flask import Flask, Response, jsonify, request, send_file
except ImportError:  # pragma: no cover
    Flask = None

from autoprober.cnc import CNC
from autoprober import kill
from autoprober.logging import LOG_PATH
from autoprober.paths import CALIBRATION_PATH
from autoprober.scope import Scope
from autoprober.safety import EndstopMonitor, EndstopState, classify_endstop_voltage, describe_endstop_state


APP_ROOT = Path(__file__).resolve().parents[1]
HTML_PATH = APP_ROOT / "dashboard" / "index.html"
PROJECT_ROOT = APP_ROOT.parent if APP_ROOT.name == "v2" else APP_ROOT
PROBE_REVIEW_ROOT = Path(os.environ.get("AUTOPROBER_PROBE_REVIEW_ROOT", PROJECT_ROOT / "probe_review")).expanduser()
MAP_ROOT = Path(os.environ.get("AUTOPROBER_MAP_ROOT", PROJECT_ROOT / "target_map")).expanduser()
MAP_ANNOTATIONS_FILE = os.environ.get("AUTOPROBER_MAP_ANNOTATIONS", "annotations.json")
MAP_ANNOTATED_IMAGE = os.environ.get("AUTOPROBER_MAP_IMAGE", "target-map-annotated.jpg")
MAP_ANNOTATED_PREVIEW = os.environ.get("AUTOPROBER_MAP_PREVIEW", "target-map-annotated-preview.jpg")
MAP_NOTES_FILE = os.environ.get("AUTOPROBER_MAP_NOTES", "annotation-notes.md")
MAP_ALLOWED_ARTIFACTS = {
    MAP_ANNOTATIONS_FILE,
    MAP_ANNOTATED_IMAGE,
    MAP_ANNOTATED_PREVIEW,
    MAP_NOTES_FILE,
    "target-map.jpg",
    "target-map-metadata.json",
}
MICROSCOPE_SNAPSHOT_URL = os.environ.get("AUTOPROBER_MICROSCOPE_SNAPSHOT_URL", "http://127.0.0.1:8080/?action=snapshot")
MICROSCOPE_STREAM_URL = os.environ.get("AUTOPROBER_MICROSCOPE_STREAM_URL", "http://127.0.0.1:8080/?action=stream")
DEFAULT_MICROSCOPE_DEVICE = os.environ.get("AUTOPROBER_MICROSCOPE_DEV", "/dev/video0")
DEFAULT_CNC_PORT = os.environ.get("AUTOPROBER_CNC_PORT", "/dev/ttyUSB0")
SCOPE_ENDPOINT = f"{os.environ.get('AUTOPROBER_SCOPE_HOST', '127.0.0.1')}:{os.environ.get('AUTOPROBER_SCOPE_PORT', '5025')}"
CALIBRATION_CHECKED_PATH = APP_ROOT / ".calibration_checked.json"
OUTLET_ENDPOINTS = {1, 2, 3, 4, 5}
Y_OPERATOR_LIMIT_GUARD_MM = 1.0
X_HOME_LIMIT_GUARD_MM = 1.0


def _json_from_process(result):
    return {
        "returncode": result.returncode,
        "stdout": result.stdout or "",
        "stderr": result.stderr or "",
    }


def _json_from_outlet_process(result):
    return {
        "returncode": result.returncode,
        "stderr_tail": "\n".join((result.stderr or "").splitlines()[-5:]),
    }


def _parse_onoff(stdout: str):
    match = re.search(r"\bOnOff:\s*(TRUE|FALSE)\b", stdout or "", re.IGNORECASE)
    if not match:
        return None
    return match.group(1).upper() == "TRUE"


def _dashboard_log(message: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] [dashboard] {message}"
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def _clean_log_message(message: str, limit: int = 180) -> str:
    cleaned = re.sub(r"\s+", " ", str(message or "")).strip()
    return cleaned[:limit] if cleaned else "event"


def _kill_response():
    return jsonify({"success": False, "error": f"KILL latched: {kill.kill_reason()}", "kill_active": True}), 423


def _require_no_kill():
    if kill.kill_active():
        return _kill_response()
    return None


def _kill_autoprober_jobs() -> None:
    patterns = [
        "apps/home.py",
        "apps/calibrate.py",
        "apps/preflight.py",
    ]
    for pattern in patterns:
        subprocess.run(["sudo", "pkill", "-f", pattern], capture_output=True, text=True)


def _latch_kill(reason: str) -> None:
    reason = _clean_log_message(reason, limit=240)
    kill.latch_kill(reason)
    _dashboard_log(f"KILL latched: {reason}")
    _kill_autoprober_jobs()


def _maybe_latch_cnc_alarm(status: dict) -> None:
    real_pins = _real_limit_pins(status)
    state = str(status.get("state", ""))
    if state.lower().startswith("alarm"):
        if real_pins:
            _latch_kill(f"CNC Alarm with real limit pins {','.join(real_pins)}")
        else:
            _latch_kill("CNC Alarm state")


def _real_limit_pins(status: dict) -> list[str]:
    pins = status.get("pins") or []
    if isinstance(pins, set):
        pins = sorted(pins)
    return [pin for pin in pins if pin in {"X", "Y", "Z"}]


def _status_is_alarm(status: dict) -> bool:
    return str(status.get("state", "")).lower().startswith("alarm")


def _jog_target_mpos(pre_status: dict, axis: str, distance: float) -> tuple[float, float, float]:
    mpos = pre_status.get("mpos")
    if not isinstance(mpos, (list, tuple)) or len(mpos) < 3:
        raise RuntimeError(f"CNC status missing MPos before jog: {pre_status}")
    target = [float(mpos[0]), float(mpos[1]), float(mpos[2])]
    target[{"X": 0, "Y": 1, "Z": 2}[axis]] += distance
    return (target[0], target[1], target[2])


def _position_near(status: dict, target: tuple[float, float, float], tolerance: float = 0.05) -> bool:
    mpos = status.get("mpos")
    if not isinstance(mpos, (list, tuple)) or len(mpos) < 3:
        return False
    return all(abs(float(mpos[index]) - target[index]) <= tolerance for index in range(3))


def _wait_for_jog_complete(cnc: CNC, target: tuple[float, float, float], timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    last_status = None
    while time.time() < deadline:
        last_status = cnc.get_status()
        if _status_is_alarm(last_status) or _real_limit_pins(last_status):
            return last_status
        if str(last_status.get("state", "")) == "Idle" and _position_near(last_status, target):
            return last_status
        time.sleep(0.1)
    raise RuntimeError(f"timed out waiting for jog target {target}; last status={last_status}")


def _run_app(script_name: str, timeout: int = 120):
    if kill.kill_active():
        raise RuntimeError(f"KILL latched: {kill.kill_reason()}")
    _dashboard_log(f"workflow {script_name}: start")
    result = subprocess.run(
        ["python3", f"apps/{script_name}"],
        cwd=APP_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    _dashboard_log(f"workflow {script_name}: {'success' if result.returncode == 0 else 'failed'}")
    return result


def _require_confirmation():
    payload = request.get_json(silent=True) or {}
    return bool(payload.get("confirm"))


def _serialize_status(status: dict) -> dict:
    serialized = dict(status)
    if isinstance(serialized.get("pins"), set):
        serialized["pins"] = sorted(serialized["pins"])
    return serialized


def _streamer_running() -> bool:
    return subprocess.run(["pgrep", "-x", "mjpg_streamer"], capture_output=True).returncode == 0


def _device_exists(path: str) -> bool:
    return Path(path).exists()


def _microscope_video_device() -> Optional[str]:
    configured = os.environ.get("MICROSCOPE_DEV")
    if configured:
        return configured if _device_exists(configured) else None

    devices = sorted(Path("/dev").glob("video*"), key=lambda path: path.name)
    for device in devices:
        if _device_exists(str(device)):
            return str(device)
    return DEFAULT_MICROSCOPE_DEVICE if _device_exists(DEFAULT_MICROSCOPE_DEVICE) else None


def _probe_review_root() -> Path:
    return Path(PROBE_REVIEW_ROOT)


def _safe_probe_review_path(relative_path: str) -> Path:
    root = _probe_review_root().resolve()
    candidate = (root / relative_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("artifact path escapes probe review root")
    return candidate


def _map_root() -> Path:
    return Path(MAP_ROOT)


def _safe_map_artifact_path(relative_path: str) -> Path:
    if relative_path not in MAP_ALLOWED_ARTIFACTS:
        if ".." in Path(relative_path).parts:
            raise ValueError("artifact path escapes map root")
        raise FileNotFoundError("map artifact not found")
    root = _map_root().resolve()
    candidate = (root / relative_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("artifact path escapes map root")
    return candidate


def _load_json_file(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _write_json_file(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _load_candidates() -> list[dict]:
    data = _load_json_file(_probe_review_root() / "candidates.json", [])
    return data if isinstance(data, list) else []


def _write_candidates(candidates: list[dict]) -> None:
    _write_json_file(_probe_review_root() / "candidates.json", candidates)


def _default_probe_plan() -> dict:
    return {
        "workspace": "default",
        "status": "draft",
        "coordinate_trust": "unverified",
        "approved_targets": [],
        "blocked_targets": [],
        "notes": ["Manual review workspace initialized. No candidates approved yet."],
    }


def _load_probe_plan() -> dict:
    data = _load_json_file(_probe_review_root() / "probe_plan.json", _default_probe_plan())
    return data if isinstance(data, dict) else _default_probe_plan()


def _export_probe_plan(candidates: list[dict]) -> dict:
    approved = [item.get("id") for item in candidates if item.get("id") and item.get("review_state") == "approved"]
    blocked = [
        item.get("id")
        for item in candidates
        if item.get("id") and item.get("review_state") in {"rejected", "invalid", "needs_more_context", "new"}
    ]
    plan = _load_probe_plan()
    plan.update(
        {
            "workspace": plan.get("workspace") or "default",
            "status": "draft",
            "approved_targets": approved,
            "blocked_targets": blocked,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
    )
    _write_json_file(_probe_review_root() / "probe_plan.json", plan)
    return plan


def create_app():
    if Flask is None:
        raise RuntimeError("Flask is required for the dashboard")
    app = Flask(__name__)

    @app.route("/", methods=["GET"])
    def index():
        response = send_file(HTML_PATH)
        response.headers["Cache-Control"] = "no-store, max-age=0"
        return response

    @app.route("/api/safety", methods=["GET"])
    def safety():
        try:
            with Scope(quiet=True) as scope:
                voltage = scope.measure_mean(4)
            state = classify_endstop_voltage(voltage)
            return jsonify(
                {
                    "ok": state == EndstopState.CLEAR,
                    "state": state.value,
                    "voltage": voltage,
                    "detail": describe_endstop_state(voltage),
                }
            )
        except Exception as exc:
            return jsonify({"ok": False, "state": "fault", "voltage": None, "detail": str(exc)})

    @app.route("/api/status", methods=["GET"])
    def status():
        streamer = _streamer_running()
        video_device = _microscope_video_device()
        return jsonify(
            {
                "dashboard": True,
                "mjpg_streamer": streamer,
                "microscope": {
                    "video_device": video_device or DEFAULT_MICROSCOPE_DEVICE,
                    "usb_accessible": bool(video_device and _device_exists(video_device)),
                    "streamer": streamer,
                },
                "cnc": {
                    "port": DEFAULT_CNC_PORT,
                    "usb_accessible": _device_exists(DEFAULT_CNC_PORT),
                },
            }
        )

    @app.route("/api/scope/status", methods=["GET"])
    def scope_status():
        try:
            with Scope(quiet=True) as scope:
                idn = scope.idn()
            _dashboard_log("scope status: online")
            return jsonify({"reachable": True, "idn": idn, "endpoint": SCOPE_ENDPOINT})
        except Exception as exc:
            _dashboard_log(f"scope status: offline {_clean_log_message(exc)}")
            return jsonify({"reachable": False, "error": str(exc), "endpoint": SCOPE_ENDPOINT}), 503

    @app.route("/api/log", methods=["GET"])
    def log_tail():
        if not LOG_PATH.exists():
            return Response("", mimetype="text/plain")
        return Response("\n".join(LOG_PATH.read_text(errors="ignore").splitlines()[-200:]), mimetype="text/plain")

    @app.route("/api/log/clear", methods=["POST"])
    def log_clear():
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        LOG_PATH.write_text("")
        _dashboard_log("log cleared")
        return jsonify({"success": True})

    @app.route("/api/log/download", methods=["GET"])
    def log_download():
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"autoprober-log-{timestamp}.txt"
        data = LOG_PATH.read_bytes() if LOG_PATH.exists() else b""
        return Response(
            data,
            mimetype="text/plain",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.route("/api/dashboard/event", methods=["POST"])
    def dashboard_event():
        payload = request.get_json(silent=True) or {}
        _dashboard_log(f"ui {_clean_log_message(payload.get('message'))}")
        return jsonify({"success": True})

    @app.route("/api/kill", methods=["GET"])
    def kill_status():
        return jsonify({"kill_active": kill.kill_active(), "reason": kill.kill_reason()})

    @app.route("/api/kill", methods=["POST"])
    def kill_latch():
        payload = request.get_json(silent=True) or {}
        _latch_kill(payload.get("reason") or "operator requested kill")
        return jsonify({"success": True, "kill_active": True, "reason": kill.kill_reason()})

    @app.route("/api/kill/clear", methods=["POST"])
    def kill_clear():
        kill.clear_kill()
        _dashboard_log("KILL latch cleared")
        return jsonify({"success": True, "kill_active": False})

    @app.route("/api/log/stream", methods=["GET"])
    def log_stream():
        def generate():
            lines = []
            if LOG_PATH.exists():
                lines = LOG_PATH.read_text(errors="ignore").splitlines()[-200:]
            if not lines:
                lines = ["Waiting for log data..."]
            for line in lines:
                yield f"data: {line}\n\n"

        return Response(generate(), mimetype="text/event-stream")

    @app.route("/api/probe-review", methods=["GET"])
    def probe_review():
        candidates = _load_candidates()
        plan = _load_probe_plan()
        approved = [item for item in candidates if item.get("review_state") == "approved"]
        root = _probe_review_root()
        return jsonify(
            {
                "workspace": "default",
                "root": str(root),
                "candidate_count": len(candidates),
                "approved_count": len(approved),
                "plan_exists": (root / "probe_plan.json").exists(),
                "candidate_file_exists": (root / "candidates.json").exists(),
                "plan_status": plan.get("status", "draft"),
            }
        )

    @app.route("/api/probe-review/candidates", methods=["GET"])
    def probe_review_candidates():
        return jsonify({"success": True, "workspace": "default", "candidates": _load_candidates()})

    @app.route("/api/probe-review/candidates", methods=["POST"])
    def probe_review_candidates_update():
        payload = request.get_json(silent=True) or {}
        candidate = payload.get("candidate") if "candidate" in payload else payload
        if not isinstance(candidate, dict) or not candidate.get("id"):
            return jsonify({"success": False, "error": "candidate with id is required"}), 400
        candidates = _load_candidates()
        existing = next((index for index, item in enumerate(candidates) if item.get("id") == candidate["id"]), None)
        if existing is None:
            candidates.append(candidate)
        else:
            candidates[existing] = {**candidates[existing], **candidate}
        _write_candidates(candidates)
        _dashboard_log(f"probe review {candidate['id']}: saved")
        return jsonify({"success": True, "candidate": candidate})

    @app.route("/api/probe-review/candidates/<candidate_id>/review", methods=["POST"])
    def probe_review_candidate_state(candidate_id):
        payload = request.get_json(silent=True) or {}
        review_state = payload.get("review_state")
        allowed = {"new", "needs_more_context", "approved", "rejected", "invalid"}
        if review_state not in allowed:
            return jsonify({"success": False, "error": "invalid review_state"}), 400
        candidates = _load_candidates()
        for candidate in candidates:
            if candidate.get("id") == candidate_id:
                candidate["review_state"] = review_state
                candidate["reviewed_at"] = datetime.now().isoformat(timespec="seconds")
                _write_candidates(candidates)
                _dashboard_log(f"probe review {candidate_id}: review_state={review_state}")
                return jsonify({"success": True, "candidate": candidate})
        return jsonify({"success": False, "error": "candidate not found"}), 404

    @app.route("/api/probe-review/plan", methods=["GET"])
    def probe_review_plan():
        return jsonify({"success": True, "workspace": "default", "plan": _load_probe_plan()})

    @app.route("/api/probe-review/plan/export", methods=["POST"])
    def probe_review_plan_export():
        plan = _export_probe_plan(_load_candidates())
        _dashboard_log(
            f"probe review plan export: {len(plan.get('approved_targets', []))} approved, "
            f"{len(plan.get('blocked_targets', []))} blocked"
        )
        return jsonify({"success": True, "plan": plan})

    @app.route("/api/probe-review/artifact/<path:artifact_path>", methods=["GET"])
    def probe_review_artifact(artifact_path):
        try:
            path = _safe_probe_review_path(artifact_path)
        except ValueError as exc:
            return jsonify({"success": False, "error": str(exc)}), 400
        if not path.exists() or not path.is_file():
            return jsonify({"success": False, "error": "artifact not found"}), 404
        return send_file(path)

    @app.route("/api/map", methods=["GET"])
    def map_summary():
        annotations_path = _map_root() / MAP_ANNOTATIONS_FILE
        annotations = _load_json_file(annotations_path, {})
        if not isinstance(annotations, dict):
            annotations = {}
        labels = annotations.get("labels") if isinstance(annotations.get("labels"), list) else []
        pin_markers = annotations.get("pin_markers") if isinstance(annotations.get("pin_markers"), list) else []
        return jsonify(
            {
                "success": True,
                "workspace": "default",
                "root": str(_map_root()),
                "source_image": annotations.get("source_image", "target_map/target-map.jpg"),
                "image_preview_url": f"/api/map/artifact/{MAP_ANNOTATED_PREVIEW}",
                "image_full_url": f"/api/map/artifact/{MAP_ANNOTATED_IMAGE}",
                "annotations_url": f"/api/map/artifact/{MAP_ANNOTATIONS_FILE}",
                "notes_url": f"/api/map/artifact/{MAP_NOTES_FILE}",
                "coordinate_method": annotations.get("coordinate_method", "unknown"),
                "coordinate_trust": annotations.get("trust", "review-only; not approved probe targets"),
                "bounds": annotations.get("bounds", {}),
                "z": annotations.get("z"),
                "label_count": len(labels),
                "labels": labels,
                "pin_marker_count": len(pin_markers),
                "pin_markers": pin_markers,
            }
        )

    @app.route("/api/map/artifact/<path:artifact_path>", methods=["GET"])
    def map_artifact(artifact_path):
        try:
            path = _safe_map_artifact_path(artifact_path)
        except ValueError as exc:
            return jsonify({"success": False, "error": str(exc)}), 400
        except FileNotFoundError as exc:
            return jsonify({"success": False, "error": str(exc)}), 404
        if not path.exists() or not path.is_file():
            return jsonify({"success": False, "error": "map artifact not found"}), 404
        return send_file(path)

    @app.route("/api/calibration", methods=["GET"])
    def calibration():
        checked = None
        if CALIBRATION_CHECKED_PATH.exists():
            try:
                checked = json.loads(CALIBRATION_CHECKED_PATH.read_text())
            except json.JSONDecodeError:
                checked = {"valid": False}
        if not CALIBRATION_PATH.exists():
            return jsonify(
                {
                    "exists": False,
                    "path": str(CALIBRATION_PATH),
                    "operator_checked": bool(checked),
                    "checked": checked,
                    "checked_mtime": CALIBRATION_CHECKED_PATH.stat().st_mtime
                    if CALIBRATION_CHECKED_PATH.exists()
                    else None,
                }
            )
        try:
            data = json.loads(CALIBRATION_PATH.read_text())
        except json.JSONDecodeError as exc:
            return jsonify({"exists": True, "valid": False, "error": str(exc), "path": str(CALIBRATION_PATH)}), 500
        return jsonify(
            {
                "exists": True,
                "valid": True,
                "path": str(CALIBRATION_PATH),
                "mtime": CALIBRATION_PATH.stat().st_mtime,
                "calibration": data,
                "operator_checked": bool(checked),
                "checked": checked,
                "checked_mtime": CALIBRATION_CHECKED_PATH.stat().st_mtime
                if CALIBRATION_CHECKED_PATH.exists()
                else None,
            }
        )

    @app.route("/api/calibration/check", methods=["POST"])
    def calibration_check():
        payload = request.get_json(silent=True) or {}
        reason = str(payload.get("reason") or "operator confirmed unchanged")
        marker = {
            "checked_at": datetime.now().isoformat(timespec="seconds"),
            "reason": reason,
            "calibration_file_exists": CALIBRATION_PATH.exists(),
        }
        CALIBRATION_CHECKED_PATH.write_text(json.dumps(marker, indent=2) + "\n")
        _dashboard_log(f"calibration: operator checked ({reason})")
        return jsonify({"success": True, "checked": marker})

    @app.route("/api/microscope/stream", methods=["GET"])
    def microscope_stream():
        def generate():
            with urllib.request.urlopen(MICROSCOPE_STREAM_URL, timeout=10) as stream:
                while True:
                    chunk = stream.read(8192)
                    if not chunk:
                        break
                    yield chunk

        return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=boundarydonotcross")

    @app.route("/api/microscope/snapshot", methods=["GET"])
    def microscope_snapshot():
        with urllib.request.urlopen(MICROSCOPE_SNAPSHOT_URL, timeout=10) as snapshot:
            return Response(snapshot.read(), mimetype="image/jpeg")

    @app.route("/api/microscope/start", methods=["POST"])
    def microscope_start():
        _dashboard_log("microscope start: requested")
        running = _streamer_running()
        video_device = _microscope_video_device()
        if not video_device:
            _dashboard_log("microscope start: no video device")
            return jsonify({"success": False, "running": running, "error": "No microscope video device found"}), 503
        if not running:
            subprocess.Popen(
                [
                    "sudo",
                    "mjpg_streamer",
                    "-i",
                    f"input_uvc.so -d {video_device} -r 1600x1200 -f 15",
                    "-o",
                    "output_http.so -p 8080 -w /usr/local/share/mjpg-streamer/www",
                ],
                cwd=APP_ROOT,
            )
            for _ in range(20):
                if _streamer_running():
                    break
                time.sleep(0.25)
        running = _streamer_running()
        kill_active = kill.kill_active()
        state = "running" if running else "not running"
        _dashboard_log(f"microscope start: {state} device={video_device}")
        return jsonify({"success": True, "running": running, "video_device": video_device, "kill_active": kill_active})

    @app.route("/api/microscope/stop", methods=["POST"])
    def microscope_stop():
        _dashboard_log("microscope stop: requested")
        result = subprocess.run(["sudo", "pkill", "mjpg_streamer"], capture_output=True, text=True)
        _dashboard_log(f"microscope stop: {'success' if result.returncode in (0, 1) else 'failed'}")
        return jsonify({"success": result.returncode in (0, 1), **_json_from_process(result)})

    @app.route("/api/scope/test", methods=["POST"])
    def scope_test():
        try:
            with Scope(quiet=True) as scope:
                idn = scope.idn()
                ch1_mean = scope.measure_mean(1)
                ch4_mean = scope.measure_mean(4)
            state = classify_endstop_voltage(ch4_mean)
            _dashboard_log("scope test: success")
            return jsonify(
                {
                    "success": True,
                    "idn": idn,
                    "ch1_mean": ch1_mean,
                    "ch4_mean": ch4_mean,
                    "safety_state": state.value,
                    "safety_detail": describe_endstop_state(ch4_mean),
                }
            )
        except Exception as exc:
            _dashboard_log(f"scope test: failed {_clean_log_message(exc)}")
            return jsonify({"success": False, "error": str(exc)}), 503

    @app.route("/api/cnc/test", methods=["POST"])
    def cnc_test():
        cnc = CNC()
        try:
            cnc.connect()
            status_data = cnc.get_status()
            _maybe_latch_cnc_alarm(status_data)
            _dashboard_log(f"cnc test: success state={status_data.get('state', 'unknown')}")
            return jsonify({"success": True, "status": _serialize_status(status_data)})
        except Exception as exc:
            _dashboard_log(f"cnc test: failed {_clean_log_message(exc)}")
            return jsonify({"success": False, "error": str(exc)}), 503
        finally:
            cnc.close()

    @app.route("/api/cnc/settings", methods=["GET"])
    def cnc_settings():
        cnc = CNC()
        try:
            cnc.connect()
            settings = cnc.read_settings()
            wanted = {key: settings.get(key) for key in ("3", "5", "21", "22", "23", "130", "131", "132")}
            _dashboard_log("cnc settings: read")
            return jsonify({"success": True, "settings": settings, "wanted": wanted})
        except Exception as exc:
            _dashboard_log(f"cnc settings: failed {_clean_log_message(exc)}")
            return jsonify({"success": False, "error": str(exc)}), 503
        finally:
            cnc.close()

    @app.route("/api/cnc/unlock", methods=["POST"])
    def cnc_unlock():
        _dashboard_log("cnc unlock: requested")
        scope = Scope(quiet=True)
        cnc = CNC()
        try:
            scope.connect()
            voltage = scope.measure_mean(4)
            state = classify_endstop_voltage(voltage)
            if state != EndstopState.CLEAR:
                error = f"STOP: {describe_endstop_state(voltage)}"
                _dashboard_log(f"cnc unlock: blocked {error}")
                _latch_kill(f"Channel 4 not clear before unlock: {describe_endstop_state(voltage)}")
                return jsonify({"success": False, "error": error}), 409

            cnc.connect()
            pre_status = cnc.get_status()
            real_pins = _real_limit_pins(pre_status)
            if real_pins:
                error = f"CNC real limit pin active before unlock: {','.join(real_pins)}"
                _dashboard_log(f"cnc unlock: blocked {error}")
                _latch_kill(error)
                return jsonify({"success": False, "error": error, "status": _serialize_status(pre_status)}), 409

            cnc.unlock()
            time.sleep(0.2)
            post_status = cnc.get_status()
            real_pins = _real_limit_pins(post_status)
            if _status_is_alarm(post_status):
                error = f"CNC remains in Alarm after unlock: {post_status.get('raw', post_status)}"
                _dashboard_log(f"cnc unlock: failed {error}")
                _latch_kill(error)
                return jsonify({"success": False, "error": error, "status": _serialize_status(post_status)}), 409
            if real_pins:
                error = f"CNC real limit pin active after unlock: {','.join(real_pins)}"
                _dashboard_log(f"cnc unlock: failed {error}")
                _latch_kill(error)
                return jsonify({"success": False, "error": error, "status": _serialize_status(post_status)}), 409

            if kill.kill_active():
                kill.clear_kill()
                _dashboard_log("KILL latch cleared after CNC unlock")
            _dashboard_log(f"cnc unlock: success state={post_status.get('state', 'unknown')}")
            return jsonify({"success": True, "status": _serialize_status(post_status), "kill_active": kill.kill_active()})
        except Exception as exc:
            _dashboard_log(f"cnc unlock: failed {_clean_log_message(exc)}")
            return jsonify({"success": False, "error": str(exc)}), 503
        finally:
            cnc.close()
            scope.close()

    @app.route("/api/cnc/jog", methods=["POST"])
    def cnc_jog():
        guard = _require_no_kill()
        if guard:
            return guard
        payload = request.get_json(silent=True) or {}
        axis = str(payload.get("axis", "")).upper()
        try:
            distance = float(payload.get("distance", 0))
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "distance must be numeric"}), 400
        if axis not in {"X", "Y", "Z"}:
            return jsonify({"success": False, "error": "axis must be X, Y, or Z"}), 400
        if distance == 0 or abs(distance) > 10:
            return jsonify({"success": False, "error": "distance must be nonzero and no more than 10 mm"}), 400

        _dashboard_log(f"cnc jog: requested axis={axis} distance={distance}")
        scope = Scope(quiet=True)
        cnc = CNC()
        monitor = None
        try:
            scope.connect()
            voltage = scope.measure_mean(4)
            state = classify_endstop_voltage(voltage)
            if state != EndstopState.CLEAR:
                _dashboard_log(f"cnc jog: blocked {describe_endstop_state(voltage)}")
                _latch_kill(f"Channel 4 not clear before jog: {describe_endstop_state(voltage)}")
                return jsonify({"success": False, "error": f"STOP: {describe_endstop_state(voltage)}"}), 409

            cnc.connect()
            pre_status = cnc.get_status()
            _maybe_latch_cnc_alarm(pre_status)
            real_pins = _real_limit_pins(pre_status)
            if _status_is_alarm(pre_status):
                error = f"CNC is in Alarm before jog: {pre_status.get('raw', pre_status)}"
                _dashboard_log(f"cnc jog: blocked {error}")
                if real_pins:
                    _latch_kill(f"CNC Alarm before jog with real limit pins {','.join(real_pins)}")
                return jsonify({"success": False, "error": error, "status": _serialize_status(pre_status)}), 409
            if real_pins:
                error = f"CNC real limit pin active before jog: {','.join(real_pins)}"
                _dashboard_log(f"cnc jog: blocked {error}")
                _latch_kill(error)
                return jsonify({"success": False, "error": error, "status": _serialize_status(pre_status)}), 409

            mpos = pre_status.get("mpos") or ()
            if axis == "X" and distance > 0 and len(mpos) >= 1 and mpos[0] >= -X_HOME_LIMIT_GUARD_MM:
                error = (
                    "X+ jog blocked at homed-edge X limit guard "
                    f"(MPos X={mpos[0]:.3f}, guard={X_HOME_LIMIT_GUARD_MM:.3f})"
                )
                _dashboard_log(f"cnc jog: blocked {error}")
                return jsonify({"success": False, "error": error, "status": _serialize_status(pre_status)}), 409
            if axis == "Y" and distance > 0 and len(mpos) >= 2 and mpos[1] >= -Y_OPERATOR_LIMIT_GUARD_MM:
                error = (
                    "Y+ jog blocked at operator-side Y limit guard "
                    f"(MPos Y={mpos[1]:.3f}, guard={Y_OPERATOR_LIMIT_GUARD_MM:.3f})"
                )
                _dashboard_log(f"cnc jog: blocked {error}")
                return jsonify({"success": False, "error": error, "status": _serialize_status(pre_status)}), 409

            monitor = EndstopMonitor(scope, poll_interval=0.1, hold_callback=cnc.feed_hold)
            monitor.start()
            kwargs = {"feed": 500}
            if axis == "X":
                kwargs["dx"] = distance
            elif axis == "Y":
                kwargs["dy"] = distance
            else:
                kwargs["dz"] = distance
            target_mpos = _jog_target_mpos(pre_status, axis, distance)
            cnc.move_relative(**kwargs)
            post_status = _wait_for_jog_complete(cnc, target_mpos, timeout=30)
            monitor.require_clear()
            _maybe_latch_cnc_alarm(post_status)
            real_pins = _real_limit_pins(post_status)
            if _status_is_alarm(post_status):
                error = f"CNC entered Alarm after jog: {post_status.get('raw', post_status)}"
                _dashboard_log(f"cnc jog: failed {error}")
                _latch_kill(error)
                return jsonify({"success": False, "error": error, "status": _serialize_status(post_status)}), 409
            if real_pins:
                error = f"CNC real limit pin active after jog: {','.join(real_pins)}"
                _dashboard_log(f"cnc jog: failed {error}")
                _latch_kill(error)
                return jsonify({"success": False, "error": error, "status": _serialize_status(post_status)}), 409
            _dashboard_log(f"cnc jog: success axis={axis} distance={distance}")
            return jsonify({"success": True, "axis": axis, "distance": distance, "status": _serialize_status(post_status)})
        except Exception as exc:
            status_code = 409 if monitor and monitor.triggered else 503
            _dashboard_log(f"cnc jog: failed {_clean_log_message(exc)}")
            if monitor and monitor.triggered:
                _latch_kill(f"Channel 4 triggered during jog: {_clean_log_message(exc)}")
            return jsonify({"success": False, "error": str(exc)}), status_code
        finally:
            if monitor:
                monitor.stop()
            cnc.close()
            scope.close()

    @app.route("/api/outlet/state", methods=["GET"])
    def outlet_state():
        states = {}
        for endpoint in sorted(OUTLET_ENDPOINTS):
            result = subprocess.run(
                ["sudo", "chip-tool", "onoff", "read", "on-off", "1", str(endpoint)],
                capture_output=True,
                text=True,
                timeout=20,
            )
            states[str(endpoint)] = {
                "success": result.returncode == 0,
                "on_off": _parse_onoff(result.stdout),
                **_json_from_outlet_process(result),
            }
        ok_count = sum(1 for entry in states.values() if entry["success"])
        on_count = sum(1 for entry in states.values() if entry["on_off"] is True)
        _dashboard_log(f"outlet state read: {on_count} on, {ok_count}/{len(states)} readable")
        return jsonify({"success": True, "outlets": states})

    @app.route("/api/outlet/<int:endpoint>", methods=["POST"])
    def outlet_control(endpoint):
        if endpoint not in OUTLET_ENDPOINTS:
            return jsonify({"success": False, "error": "unknown outlet endpoint"}), 400
        payload = request.get_json(silent=True) or {}
        action = payload.get("action", "toggle")
        if action not in {"on", "off", "toggle"}:
            return jsonify({"success": False, "error": "action must be on, off, or toggle"}), 400
        result = subprocess.run(
            ["sudo", "chip-tool", "onoff", action, "1", str(endpoint)],
            capture_output=True,
            text=True,
            timeout=20,
        )
        _dashboard_log(f"outlet {endpoint} {action}: {'success' if result.returncode == 0 else 'failed'}")
        return jsonify({"success": result.returncode == 0, "endpoint": endpoint, "action": action, **_json_from_outlet_process(result)}), (
            200 if result.returncode == 0 else 502
        )

    @app.route("/api/workflow/preflight", methods=["POST"])
    def workflow_preflight():
        guard = _require_no_kill()
        if guard:
            return guard
        result = _run_app("preflight.py", timeout=90)
        return jsonify({"success": result.returncode == 0, **_json_from_process(result)}), (
            200 if result.returncode == 0 else 502
        )

    @app.route("/api/workflow/home", methods=["POST"])
    def workflow_home():
        guard = _require_no_kill()
        if guard:
            return guard
        if not _require_confirmation():
            return jsonify({"success": False, "error": "home requires explicit confirmation"}), 409
        result = _run_app("home.py", timeout=180)
        return jsonify({"success": result.returncode == 0, **_json_from_process(result)}), (
            200 if result.returncode == 0 else 502
        )

    @app.route("/api/workflow/calibrate", methods=["POST"])
    def workflow_calibrate():
        guard = _require_no_kill()
        if guard:
            return guard
        if not _require_confirmation():
            return jsonify({"success": False, "error": "calibration requires explicit confirmation"}), 409
        result = _run_app("calibrate.py", timeout=180)
        return jsonify({"success": result.returncode == 0, **_json_from_process(result)}), (
            200 if result.returncode == 0 else 502
        )

    return app


if __name__ == "__main__":
    host = os.environ.get("AUTOPROBER_DASHBOARD_HOST", "0.0.0.0")
    port = int(os.environ.get("AUTOPROBER_DASHBOARD_PORT", "5000"))
    create_app().run(host=host, port=port)
