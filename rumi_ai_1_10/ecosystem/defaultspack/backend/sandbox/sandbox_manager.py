from __future__ import annotations

import base64
import binascii
import json
import os
import platform
import struct
import tempfile
import threading
import time
import uuid
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


REGISTRY_SCHEMA_VERSION = 1
READY = "ready"
DESTROYED = "destroyed"
ERROR = "error"
TERMINAL_STATUSES = {DESTROYED, ERROR}
SUPPORTED_MODEL_MODES = {"fast", "heavy"}
STATE_DIR_ENV = "RUMI_DEFAULTSPACK_SANDBOX_STATE_DIR"


@dataclass
class SandboxInstance:
    sandbox_id: str = ""
    image: str = "ubuntu:22.04"
    display: bool = True
    status: str = "ready"
    created_at: float = 0.0
    updated_at: float = 0.0
    destroyed_at: Optional[float] = None
    last_activity_at: Optional[float] = None
    last_error: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.sandbox_id:
            self.sandbox_id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = time.time()
        if not self.updated_at:
            self.updated_at = self.created_at
        if self.status not in {READY, DESTROYED, ERROR}:
            self.last_error = f"Unknown persisted status {self.status!r}; marked error"
            self.status = ERROR
            self.updated_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sandbox_id": self.sandbox_id,
            "image": self.image,
            "display": self.display,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "destroyed_at": self.destroyed_at,
            "last_activity_at": self.last_activity_at,
            "last_error": self.last_error,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SandboxInstance":
        return cls(
            sandbox_id=str(data.get("sandbox_id") or ""),
            image=str(data.get("image") or "ubuntu:22.04"),
            display=bool(data.get("display", True)),
            status=str(data.get("status") or READY),
            created_at=_float_or_zero(data.get("created_at")),
            updated_at=_float_or_zero(data.get("updated_at")),
            destroyed_at=_optional_float(data.get("destroyed_at")),
            last_activity_at=_optional_float(data.get("last_activity_at")),
            last_error=str(data.get("last_error")) if data.get("last_error") is not None else None,
        )

    def touch(self, *, status: Optional[str] = None, error: Optional[str] = None) -> None:
        now = time.time()
        self.updated_at = now
        self.last_activity_at = now
        if status is not None:
            self.status = status
        if error is not None:
            self.last_error = error


class SandboxManager:
    def __init__(
        self,
        state_dir: str | Path | None = None,
        *,
        registry_path: str | Path | None = None,
        gui_backend: Any | None = None,
    ) -> None:
        self.state_dir = Path(state_dir) if state_dir is not None else self._default_state_dir()
        self.registry_path = (
            Path(registry_path) if registry_path is not None else self.state_dir / "sandboxes.json"
        )
        self._gui_backend = gui_backend
        self._lock = threading.RLock()
        self._instances: Dict[str, SandboxInstance] = {}
        self._model_mode: str = "fast"
        self._load_registry()

    def create(self, image: str = "ubuntu:22.04", display: bool = True) -> Dict[str, Any]:
        image = str(image or "").strip() or "ubuntu:22.04"
        with self._lock:
            inst = SandboxInstance(image=image, display=bool(display), status=READY)
            self._instances[inst.sandbox_id] = inst
            self._save_registry()
            return {
                "ok": True,
                "created": True,
                "sandbox_id": inst.sandbox_id,
                "status": inst.status,
                "registry_path": str(self.registry_path),
            }

    def destroy(self, sandbox_id: str) -> Dict[str, Any]:
        with self._lock:
            inst = self._instances.get(str(sandbox_id))
            if inst is None:
                return self._not_found(sandbox_id)
            if inst.status != DESTROYED:
                now = time.time()
                inst.status = DESTROYED
                inst.destroyed_at = now
                inst.updated_at = now
                inst.last_activity_at = now
                inst.last_error = None
                self._save_registry()
            return {
                "ok": True,
                "destroyed": True,
                "sandbox_id": inst.sandbox_id,
                "status": inst.status,
            }

    def screenshot(self, sandbox_id: str) -> Dict[str, Any]:
        with self._lock:
            inst, error = self._ready_instance(sandbox_id)
            if error is not None:
                return error
            assert inst is not None
            inst.touch()
            self._save_registry()

        backend_result = self._backend_screenshot(inst)
        if backend_result is not None:
            return backend_result

        image_base64 = _fallback_png_base64()
        data_uri = f"data:image/png;base64,{image_base64}"
        return {
            "ok": True,
            "sandbox_id": inst.sandbox_id,
            "status": inst.status,
            "screenshot": data_uri,
            "data_uri": data_uri,
            "base64": image_base64,
            "image_base64": image_base64,
            "format": "png",
            "mime_type": "image/png",
            "width": 2,
            "height": 2,
            "source": "local_fallback",
            "gui_backend": False,
        }

    def click(self, sandbox_id: str, x: int, y: int) -> Dict[str, Any]:
        with self._lock:
            inst, error = self._ready_instance(sandbox_id)
            if error is not None:
                return error
            assert inst is not None
            inst.touch()
            self._save_registry()
        return {
            "ok": True,
            "clicked": True,
            "recorded": True,
            "sandbox_id": inst.sandbox_id,
            "x": x,
            "y": y,
        }

    def type_text(self, sandbox_id: str, text: str) -> Dict[str, Any]:
        with self._lock:
            inst, error = self._ready_instance(sandbox_id)
            if error is not None:
                return error
            assert inst is not None
            inst.touch()
            self._save_registry()
        return {
            "ok": True,
            "typed": True,
            "recorded": True,
            "sandbox_id": inst.sandbox_id,
            "text": text,
        }

    def scroll(self, sandbox_id: str, direction: str = "down", amount: int = 3) -> Dict[str, Any]:
        with self._lock:
            inst, error = self._ready_instance(sandbox_id)
            if error is not None:
                return error
            assert inst is not None
            inst.touch()
            self._save_registry()
        return {
            "ok": True,
            "scrolled": True,
            "recorded": True,
            "sandbox_id": inst.sandbox_id,
            "direction": direction,
            "amount": amount,
        }

    def set_model_mode(self, mode: str) -> Dict[str, Any]:
        if mode not in SUPPORTED_MODEL_MODES:
            return {
                "ok": False,
                "error": f"Invalid mode: {mode}",
                "code": "INVALID_MODEL_MODE",
                "status_code": 400,
            }
        with self._lock:
            self._model_mode = mode
            self._save_registry()
        return {"ok": True, "mode": mode}

    def status(self, sandbox_id: str) -> Dict[str, Any]:
        with self._lock:
            inst = self._instances.get(str(sandbox_id))
            if inst is None:
                return self._not_found(sandbox_id)
            return {"ok": True, **inst.to_dict()}

    def list_instances(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [instance.to_dict() for instance in self._instances.values()]

    @staticmethod
    def _default_state_dir() -> Path:
        override = os.environ.get(STATE_DIR_ENV)
        if override:
            return Path(override).expanduser()

        xdg_state = os.environ.get("XDG_STATE_HOME")
        if xdg_state:
            return Path(xdg_state).expanduser() / "rumi" / "defaultspack" / "sandbox"

        system = platform.system().lower()
        home = Path.home()
        if system == "darwin":
            return home / "Library" / "Application Support" / "Rumi AI" / "defaultspack" / "sandbox"
        if system == "windows":
            local_app_data = os.environ.get("LOCALAPPDATA")
            if local_app_data:
                return Path(local_app_data) / "Rumi AI" / "defaultspack" / "sandbox"
        if home:
            return home / ".local" / "state" / "rumi" / "defaultspack" / "sandbox"
        return Path(tempfile.gettempdir()) / "rumi" / "defaultspack" / "sandbox"

    def _load_registry(self) -> None:
        with self._lock:
            if not self.registry_path.is_file():
                return
            try:
                data = json.loads(self.registry_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                backup_path = self.registry_path.with_suffix(f".corrupt-{int(time.time())}.json")
                try:
                    self.registry_path.replace(backup_path)
                except OSError:
                    pass
                self._instances = {}
                self._model_mode = "fast"
                self._load_error = str(exc)
                return

            if isinstance(data, dict):
                raw_instances = data.get("instances", {})
                mode = str(data.get("model_mode") or "fast")
                self._model_mode = mode if mode in SUPPORTED_MODEL_MODES else "fast"
            else:
                raw_instances = data

            instances: Dict[str, SandboxInstance] = {}
            if isinstance(raw_instances, dict):
                iterable = raw_instances.values()
            elif isinstance(raw_instances, list):
                iterable = raw_instances
            else:
                iterable = []
            for raw in iterable:
                if not isinstance(raw, dict):
                    continue
                inst = SandboxInstance.from_dict(raw)
                instances[inst.sandbox_id] = inst
            self._instances = instances

    def _save_registry(self) -> None:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.registry_path.parent.chmod(0o700)
        except OSError:
            pass
        payload = {
            "schema_version": REGISTRY_SCHEMA_VERSION,
            "model_mode": self._model_mode,
            "updated_at": time.time(),
            "instances": {
                sandbox_id: inst.to_dict()
                for sandbox_id, inst in sorted(self._instances.items())
            },
        }
        tmp = self.registry_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        try:
            tmp.chmod(0o600)
        except OSError:
            pass
        tmp.replace(self.registry_path)

    def _ready_instance(
        self, sandbox_id: str
    ) -> tuple[Optional[SandboxInstance], Optional[Dict[str, Any]]]:
        inst = self._instances.get(str(sandbox_id))
        if inst is None:
            return None, self._not_found(sandbox_id)
        if inst.status in TERMINAL_STATUSES:
            return None, {
                "ok": False,
                "error": f"Sandbox is {inst.status}: {sandbox_id}",
                "code": "SANDBOX_NOT_RUNNING",
                "status_code": 409,
                "sandbox_id": str(sandbox_id),
                "status": inst.status,
            }
        return inst, None

    @staticmethod
    def _not_found(sandbox_id: str) -> Dict[str, Any]:
        return {
            "ok": False,
            "error": f"Sandbox not found: {sandbox_id}",
            "code": "SANDBOX_NOT_FOUND",
            "status_code": 404,
            "sandbox_id": str(sandbox_id),
        }

    def _backend_screenshot(self, inst: SandboxInstance) -> Optional[Dict[str, Any]]:
        if self._gui_backend is None or not hasattr(self._gui_backend, "screenshot"):
            return None
        try:
            result = self._gui_backend.screenshot(inst.sandbox_id)
        except Exception as exc:
            return {
                "ok": False,
                "error": f"GUI backend screenshot failed: {exc}",
                "code": "SANDBOX_SCREENSHOT_FAILED",
                "status_code": 502,
                "sandbox_id": inst.sandbox_id,
                "status": inst.status,
            }
        if not isinstance(result, dict):
            return {
                "ok": False,
                "error": "GUI backend screenshot returned an invalid payload",
                "code": "SANDBOX_SCREENSHOT_FAILED",
                "status_code": 502,
                "sandbox_id": inst.sandbox_id,
                "status": inst.status,
            }
        result.setdefault("ok", True)
        result.setdefault("sandbox_id", inst.sandbox_id)
        result.setdefault("status", inst.status)
        result.setdefault("gui_backend", True)
        return result


def _float_or_zero(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fallback_png_base64() -> str:
    return base64.b64encode(_fallback_png_bytes()).decode("ascii")


def _fallback_png_bytes() -> bytes:
    width = 2
    height = 2
    pixels = [
        (32, 36, 44, 255),
        (98, 157, 207, 255),
        (44, 54, 62, 255),
        (121, 196, 149, 255),
    ]
    rows = []
    for row_index in range(height):
        start = row_index * width
        row_pixels = pixels[start : start + width]
        rows.append(b"\x00" + b"".join(bytes(pixel) for pixel in row_pixels))

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack("!IIBBBBB", width, height, 8, 6, 0, 0, 0)
    idat = zlib.compress(b"".join(rows), level=9)
    return (
        signature
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    checksum = binascii.crc32(kind)
    checksum = binascii.crc32(data, checksum) & 0xFFFFFFFF
    return struct.pack("!I", len(data)) + kind + data + struct.pack("!I", checksum)
