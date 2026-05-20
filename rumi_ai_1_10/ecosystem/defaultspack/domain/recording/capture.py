from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

from blocks._common import gen_id, timestamp


_LOOPBACK_RE = re.compile(r"blackhole|soundflower|loopback|system audio|background music|aggregate", re.IGNORECASE)


class RecordingCaptureService:
    def __init__(
        self,
        *,
        artifact_dir: str | Path | None = None,
        sessions_path: str | Path | None = None,
        ffmpeg_path: str | None = None,
    ) -> None:
        self.artifact_dir = Path(artifact_dir) if artifact_dir is not None else self._default_artifact_dir()
        self.sessions_path = Path(sessions_path) if sessions_path is not None else self._default_sessions_path()
        self.ffmpeg_path = ffmpeg_path or shutil.which("ffmpeg")

    @staticmethod
    def _pack_root() -> Path:
        return Path(__file__).resolve().parents[2]

    @classmethod
    def _default_artifact_dir(cls) -> Path:
        override = os.environ.get("RUMI_DEFAULTSPACK_RECORDING_DIR")
        if override:
            return Path(override)
        return cls._pack_root() / "user_data" / "artifacts" / "recordings"

    @classmethod
    def _default_sessions_path(cls) -> Path:
        override = os.environ.get("RUMI_DEFAULTSPACK_RECORDING_SESSIONS_PATH")
        if override:
            return Path(override)
        return cls._pack_root() / "user_data" / "shared" / "recording" / "sessions.json"

    def list_devices(self) -> dict[str, Any]:
        devices = {"video": [], "audio": []}
        output = ""
        if self.ffmpeg_path:
            try:
                proc = subprocess.run(
                    [self.ffmpeg_path, "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=8,
                )
                output = (proc.stderr or "") + (proc.stdout or "")
                devices = self._parse_avfoundation_devices(output)
            except Exception as exc:
                output = str(exc)
        system_audio = [item for item in devices["audio"] if self._is_system_audio_device(item)]
        return {
            "ffmpeg_available": bool(self.ffmpeg_path),
            "ffmpeg_path": self.ffmpeg_path,
            "devices": devices,
            "system_audio_devices": system_audio,
            "system_audio_available": bool(system_audio),
            "raw": output[-4000:],
        }

    def start(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.ffmpeg_path:
            return {
                "status": "ffmpeg_missing",
                "is_error": True,
                "message": "ffmpeg was not found. Install ffmpeg to enable recording_capture.",
            }
        request = self._request(payload)
        devices_info = self.list_devices()
        devices = devices_info.get("devices") if isinstance(devices_info.get("devices"), dict) else {"video": [], "audio": []}
        selection = self._select_devices(request, devices)
        if selection.get("missing_system_audio_device"):
            return {
                "status": "missing_system_audio_device",
                "is_error": False,
                "message": "System audio recording needs a detectable macOS loopback/system-audio input such as BlackHole, Loopback, or Soundflower.",
                "devices": devices,
                "system_audio_available": False,
            }
        command, artifact = self._build_ffmpeg_command(request, selection)
        Path(artifact).parent.mkdir(parents=True, exist_ok=True)
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
        session = {
            "id": payload.get("session_id") or gen_id("rec_"),
            "pid": process.pid,
            "command": command,
            "artifact": artifact,
            "mime": self._mime_for_path(artifact),
            "request": request,
            "devices": selection,
            "started_at": time.time(),
            "created_at": timestamp(),
            "status": "recording",
        }
        self._upsert_session(session)
        return {
            "session_id": session["id"],
            "status": "recording",
            "pid": process.pid,
            "path": artifact,
            "mime": session["mime"],
            "devices": selection,
            "command_summary": self._command_summary(command),
        }

    def stop(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = str(payload.get("session_id") or payload.get("id") or "").strip()
        if not session_id:
            return {"status": "not_found", "is_error": True, "message": "session_id is required"}
        session = self._session(session_id)
        if not session:
            return {"status": "not_found", "is_error": True, "message": "recording session not found"}
        pid = int(session.get("pid") or 0)
        stopped = False
        if pid > 0:
            try:
                os.kill(pid, signal.SIGINT)
                stopped = True
            except ProcessLookupError:
                stopped = True
            except Exception:
                try:
                    os.kill(pid, signal.SIGTERM)
                    stopped = True
                except Exception:
                    stopped = False
        now = time.time()
        started = float(session.get("started_at") or now)
        artifact = str(session.get("artifact") or "")
        updated = {
            **session,
            "status": "stopped" if stopped else "stop_failed",
            "stopped_at": now,
            "duration_seconds": max(0.0, now - started),
            "exists": bool(artifact and Path(artifact).exists()),
            "updated_at": timestamp(),
        }
        self._upsert_session(updated)
        return {
            "session_id": session_id,
            "status": updated["status"],
            "path": artifact,
            "mime": session.get("mime") or self._mime_for_path(artifact),
            "duration_seconds": updated["duration_seconds"],
            "device_metadata": session.get("devices") or {},
            "artifact": {
                "path": artifact,
                "mime": session.get("mime") or self._mime_for_path(artifact),
                "duration_seconds": updated["duration_seconds"],
            },
        }

    def record_for(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            duration = float(payload.get("duration_seconds") or payload.get("seconds") or payload.get("duration") or 0)
        except Exception:
            duration = 0
        duration = max(0.1, min(duration, 60 * 60 * 12))
        started = self.start(payload)
        if started.get("status") != "recording":
            return started
        time.sleep(duration)
        stopped = self.stop({"session_id": started["session_id"]})
        stopped["start_result"] = started
        return stopped

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        action = str(payload.get("action") or payload.get("command") or "list_devices").strip().lower()
        if action in {"list", "devices", "list_devices"}:
            return self.list_devices()
        if action == "start":
            return self.start(payload)
        if action == "stop":
            return self.stop(payload)
        if action in {"record_for", "capture_for"}:
            return self.record_for(payload)
        return {"status": "unsupported_action", "is_error": True, "message": "unsupported recording action"}

    @classmethod
    def _parse_avfoundation_devices(cls, output: str) -> dict[str, list[dict[str, Any]]]:
        devices: dict[str, list[dict[str, Any]]] = {"video": [], "audio": []}
        section = ""
        for raw_line in str(output or "").splitlines():
            line = raw_line.strip()
            lower = line.lower()
            if "avfoundation video devices" in lower:
                section = "video"
                continue
            if "avfoundation audio devices" in lower:
                section = "audio"
                continue
            match = re.search(r"\[(\d+)\]\s+(.+)$", line)
            if section and match:
                devices[section].append({
                    "index": int(match.group(1)),
                    "name": match.group(2).strip(),
                    "kind": section,
                })
        return devices

    @staticmethod
    def _is_system_audio_device(device: dict[str, Any]) -> bool:
        return bool(_LOOPBACK_RE.search(str(device.get("name") or "")))

    @staticmethod
    def _truthy(value: Any) -> bool:
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y", "on"}
        return bool(value)

    def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        capture = payload.get("capture") if isinstance(payload.get("capture"), dict) else {}
        include_screen = self._truthy(payload.get("screen", capture.get("screen", payload.get("include_screen", True))))
        include_microphone = self._truthy(payload.get("microphone", capture.get("microphone", payload.get("include_microphone", False))))
        include_system_audio = self._truthy(payload.get("system_audio", capture.get("system_audio", payload.get("include_system_audio", False))))
        try:
            fps = int(payload.get("framerate") or payload.get("fps") or 30)
        except Exception:
            fps = 30
        return {
            "include_screen": include_screen,
            "include_microphone": include_microphone,
            "include_system_audio": include_system_audio,
            "video_device": payload.get("video_device"),
            "audio_device": payload.get("audio_device"),
            "output_dir": payload.get("output_dir"),
            "filename": payload.get("filename"),
            "framerate": max(1, min(fps, 60)),
        }

    def _select_devices(self, request: dict[str, Any], devices: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        video_devices = list(devices.get("video") or [])
        audio_devices = list(devices.get("audio") or [])
        selected_video = None
        selected_audio = None
        if request["include_screen"]:
            selected_video = self._device_by_hint(video_devices, request.get("video_device"))
            if selected_video is None:
                selected_video = next((d for d in video_devices if "screen" in str(d.get("name") or "").lower()), None)
            if selected_video is None and video_devices:
                selected_video = video_devices[0]
        if request["include_system_audio"]:
            selected_audio = self._device_by_hint(audio_devices, request.get("audio_device"), system_audio=True)
            if selected_audio is None:
                selected_audio = next((d for d in audio_devices if self._is_system_audio_device(d)), None)
            if selected_audio is None:
                return {"missing_system_audio_device": True, "video": selected_video, "audio": None}
        elif request["include_microphone"]:
            selected_audio = self._device_by_hint(audio_devices, request.get("audio_device"))
            if selected_audio is None and audio_devices:
                selected_audio = audio_devices[0]
        return {
            "video": selected_video,
            "audio": selected_audio,
            "system_audio": bool(selected_audio and self._is_system_audio_device(selected_audio)),
        }

    def _device_by_hint(
        self,
        devices: list[dict[str, Any]],
        hint: Any,
        *,
        system_audio: bool = False,
    ) -> dict[str, Any] | None:
        if hint is None or hint == "":
            return None
        text = str(hint).strip().lower()
        for device in devices:
            if text == str(device.get("index")) or text in str(device.get("name") or "").lower():
                if system_audio and not self._is_system_audio_device(device):
                    continue
                return device
        return None

    def _build_ffmpeg_command(self, request: dict[str, Any], selection: dict[str, Any]) -> tuple[list[str], str]:
        out_dir = self._resolve_output_dir(request.get("output_dir"))
        stem = str(request.get("filename") or "").strip()
        if not stem:
            stem = "recording_" + time.strftime("%Y%m%d_%H%M%S", time.localtime())
        stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("._") or "recording"
        video = selection.get("video") if isinstance(selection.get("video"), dict) else None
        audio = selection.get("audio") if isinstance(selection.get("audio"), dict) else None
        has_video = video is not None and request.get("include_screen")
        extension = ".mov" if has_video else ".m4a"
        artifact = str(out_dir / (stem + extension))
        video_ref = str(video.get("index")) if has_video else "none"
        audio_ref = str(audio.get("index")) if audio else "none"
        input_ref = f"{video_ref}:{audio_ref}" if has_video else f":{audio_ref}"
        command = [
            str(self.ffmpeg_path),
            "-y",
            "-f",
            "avfoundation",
        ]
        if has_video:
            command.extend(["-framerate", str(request.get("framerate") or 30)])
        command.extend(["-i", input_ref])
        if has_video:
            command.extend(["-c:v", "h264", "-pix_fmt", "yuv420p"])
        if audio:
            command.extend(["-c:a", "aac"])
        command.append(artifact)
        return command, artifact

    def _resolve_output_dir(self, requested: Any) -> Path:
        artifact_root = self.artifact_dir.expanduser().resolve()
        if requested in (None, ""):
            return artifact_root
        candidate = Path(str(requested)).expanduser()
        if not candidate.is_absolute():
            candidate = artifact_root / candidate
        resolved = candidate.resolve()
        if resolved != artifact_root and artifact_root not in resolved.parents:
            raise ValueError("output_dir must be inside the recording artifact directory")
        return resolved

    @staticmethod
    def _command_summary(command: list[str]) -> dict[str, Any]:
        return {
            "executable": Path(str(command[0])).name if command else "",
            "uses_overwrite": "-y" in command,
            "input_kind": "avfoundation" if "avfoundation" in command else "",
        }

    @staticmethod
    def _mime_for_path(path: str) -> str:
        lowered = str(path or "").lower()
        if lowered.endswith(".m4a"):
            return "audio/mp4"
        if lowered.endswith(".mp4"):
            return "video/mp4"
        return "video/quicktime"

    def _read_sessions(self) -> dict[str, Any]:
        try:
            data = json.loads(self.sessions_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {"schema_version": 1, "sessions": []}
        if not isinstance(data, dict):
            data = {"schema_version": 1, "sessions": []}
        if not isinstance(data.get("sessions"), list):
            data["sessions"] = []
        return data

    def _write_sessions(self, data: dict[str, Any]) -> None:
        self.sessions_path.parent.mkdir(parents=True, exist_ok=True)
        self.sessions_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _session(self, session_id: str) -> dict[str, Any] | None:
        for session in self._read_sessions().get("sessions", []):
            if isinstance(session, dict) and session.get("id") == session_id:
                return dict(session)
        return None

    def _upsert_session(self, session: dict[str, Any]) -> None:
        data = self._read_sessions()
        sessions = [item for item in data.get("sessions", []) if not (isinstance(item, dict) and item.get("id") == session.get("id"))]
        sessions.append(dict(session))
        data["sessions"] = sessions[-100:]
        self._write_sessions(data)
