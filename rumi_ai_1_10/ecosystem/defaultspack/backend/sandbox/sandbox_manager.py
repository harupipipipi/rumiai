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
from typing import Any, Callable, Dict, List, Optional


REGISTRY_SCHEMA_VERSION = 2
CREATING = "creating"
PROVISIONING = "provisioning"
STARTING = "starting"
READY = "ready"
BUSY = "busy"
STOPPING = "stopping"
STOPPED = "stopped"
FAILED = "failed"
DESTROYING = "destroying"
DESTROYED = "destroyed"
ERROR = "error"
LEGACY_PLACEHOLDER_PROVIDER = "legacy_placeholder"
LOCAL_COMPAT_PROVIDER = "local_compat"
VALID_STATUSES = {
    CREATING,
    PROVISIONING,
    STARTING,
    READY,
    BUSY,
    STOPPING,
    STOPPED,
    FAILED,
    DESTROYING,
    DESTROYED,
    ERROR,
}
RUNNING_STATUSES = {READY, BUSY}
TERMINAL_STATUSES = {DESTROYED, ERROR, FAILED}
SUPPORTED_MODEL_MODES = {"fast", "heavy"}
STATE_DIR_ENV = "RUMI_DEFAULTSPACK_SANDBOX_STATE_DIR"


@dataclass
class SandboxInstance:
    sandbox_id: str = ""
    image: str = "ubuntu:22.04"
    display: bool = True
    status: str = "ready"
    template_id: str = "tool.ephemeral"
    template_version: str = "compat"
    provider_id: str = LOCAL_COMPAT_PROVIDER
    provider_instance_id: Optional[str] = None
    runtime_id: Optional[str] = None
    capabilities: tuple[str, ...] = ()
    created_at: float = 0.0
    updated_at: float = 0.0
    started_at: Optional[float] = None
    stopped_at: Optional[float] = None
    destroyed_at: Optional[float] = None
    last_activity_at: Optional[float] = None
    last_error: Optional[str] = None
    generation: int = 1
    recovery_token_hash: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.sandbox_id:
            self.sandbox_id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = time.time()
        if not self.updated_at:
            self.updated_at = self.created_at
        if not self.provider_instance_id and self.provider_id != LEGACY_PLACEHOLDER_PROVIDER:
            self.provider_instance_id = self.sandbox_id
        if self.status not in VALID_STATUSES:
            self.last_error = f"Unknown persisted status {self.status!r}; marked error"
            self.status = ERROR
            self.updated_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sandbox_id": self.sandbox_id,
            "image": self.image,
            "display": self.display,
            "status": self.status,
            "template_id": self.template_id,
            "template_version": self.template_version,
            "provider_id": self.provider_id,
            "provider_instance_id": self.provider_instance_id,
            "runtime_id": self.runtime_id,
            "capabilities": list(self.capabilities),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "stopped_at": self.stopped_at,
            "destroyed_at": self.destroyed_at,
            "last_activity_at": self.last_activity_at,
            "last_error": self.last_error,
            "generation": self.generation,
            "recovery_token_hash": self.recovery_token_hash,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], *, legacy: bool = False) -> "SandboxInstance":
        status = str(data.get("status") or READY)
        provider_id = str(data.get("provider_id") or LOCAL_COMPAT_PROVIDER)
        provider_instance_id = data.get("provider_instance_id")
        last_error = str(data.get("last_error")) if data.get("last_error") is not None else None
        stopped_at = _optional_float(data.get("stopped_at"))
        if legacy and status == READY and not provider_instance_id:
            status = STOPPED
            provider_id = LEGACY_PLACEHOLDER_PROVIDER
            stopped_at = _optional_float(data.get("updated_at")) or _optional_float(data.get("created_at"))
            last_error = "Migrated prototype sandbox; old fake-ready instances are not treated as live."
        return cls(
            sandbox_id=str(data.get("sandbox_id") or ""),
            image=str(data.get("image") or "ubuntu:22.04"),
            display=bool(data.get("display", True)),
            status=status,
            template_id=str(data.get("template_id") or ("desktop.ubuntu" if data.get("display", True) else "tool.ephemeral")),
            template_version=str(data.get("template_version") or "compat"),
            provider_id=provider_id,
            provider_instance_id=str(provider_instance_id) if provider_instance_id is not None else None,
            runtime_id=str(data.get("runtime_id")) if data.get("runtime_id") is not None else None,
            capabilities=_string_tuple(data.get("capabilities")),
            created_at=_float_or_zero(data.get("created_at")),
            updated_at=_float_or_zero(data.get("updated_at")),
            started_at=_optional_float(data.get("started_at")),
            stopped_at=stopped_at,
            destroyed_at=_optional_float(data.get("destroyed_at")),
            last_activity_at=_optional_float(data.get("last_activity_at")),
            last_error=last_error,
            generation=max(1, int(_float_or_zero(data.get("generation") or 1))),
            recovery_token_hash=str(data.get("recovery_token_hash")) if data.get("recovery_token_hash") is not None else None,
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
        display = bool(display)
        backend_session_id, backend_error = self._create_backend_session_id(image=image)
        if backend_error is not None:
            return backend_error

        with self._lock:
            now = time.time()
            capabilities = ("sandbox.exec", "sandbox.files")
            if display:
                capabilities = capabilities + ("sandbox.desktop", "sandbox.desktop_input")
            inst = SandboxInstance(
                sandbox_id=backend_session_id or "",
                image=image,
                display=display,
                status=READY,
                template_id="desktop.ubuntu" if display else "tool.ephemeral",
                provider_id=LOCAL_COMPAT_PROVIDER,
                capabilities=capabilities,
                started_at=now,
            )
            self._instances[inst.sandbox_id] = inst
            self._save_registry()
            return {
                "ok": True,
                "created": True,
                "sandbox_id": inst.sandbox_id,
                "status": inst.status,
                "template_id": inst.template_id,
                "provider_id": inst.provider_id,
                "registry_path": str(self.registry_path),
            }

    def destroy(self, sandbox_id: str) -> Dict[str, Any]:
        with self._lock:
            inst = self._instances.get(str(sandbox_id))
            if inst is None:
                return self._not_found(sandbox_id)
            if inst.status == DESTROYED:
                return {
                    "ok": True,
                    "destroyed": True,
                    "sandbox_id": inst.sandbox_id,
                    "status": inst.status,
                }

        teardown_error = self._backend_teardown(inst)
        if teardown_error is not None:
            with self._lock:
                current = self._instances.get(inst.sandbox_id)
                if current is not None and current.status != DESTROYED:
                    now = time.time()
                    current.status = ERROR
                    current.updated_at = now
                    current.last_activity_at = now
                    current.last_error = teardown_error
                    self._save_registry()
            return {
                "ok": False,
                "destroyed": False,
                "sandbox_id": inst.sandbox_id,
                "status": ERROR,
                "error": teardown_error,
                "code": "SANDBOX_BACKEND_DESTROY_FAILED",
                "status_code": 502,
                "gui_backend": True,
            }

        with self._lock:
            inst = self._instances.get(str(sandbox_id))
            if inst is None:
                return self._not_found(sandbox_id)
            if inst.status != DESTROYED:
                now = time.time()
                inst.status = DESTROYING
                inst.status = DESTROYED
                inst.destroyed_at = now
                inst.stopped_at = now
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
        result = self._backend_input_action(
            inst,
            "click",
            "clicked",
            {"x": x, "y": y},
        )
        if result.get("ok") is True:
            self._touch_ready_instance(inst.sandbox_id)
        return result

    def type_text(self, sandbox_id: str, text: str) -> Dict[str, Any]:
        with self._lock:
            inst, error = self._ready_instance(sandbox_id)
            if error is not None:
                return error
            assert inst is not None
        result = self._backend_input_action(
            inst,
            "type_text",
            "typed",
            {"text": text},
        )
        if result.get("ok") is True:
            self._touch_ready_instance(inst.sandbox_id)
        return result

    def scroll(self, sandbox_id: str, direction: str = "down", amount: int = 3) -> Dict[str, Any]:
        with self._lock:
            inst, error = self._ready_instance(sandbox_id)
            if error is not None:
                return error
            assert inst is not None
        result = self._backend_input_action(
            inst,
            "scroll",
            "scrolled",
            {"direction": direction, "amount": amount},
        )
        if result.get("ok") is True:
            self._touch_ready_instance(inst.sandbox_id)
        return result

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
                schema_version = int(_float_or_zero(data.get("schema_version") or 0))
                self._model_mode = mode if mode in SUPPORTED_MODEL_MODES else "fast"
            else:
                raw_instances = data
                schema_version = 0

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
                inst = SandboxInstance.from_dict(raw, legacy=schema_version < REGISTRY_SCHEMA_VERSION)
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
        if inst.status not in RUNNING_STATUSES:
            return None, {
                "ok": False,
                "error": f"Sandbox is not running ({inst.status}): {sandbox_id}",
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

    def _create_backend_session_id(
        self,
        *,
        image: str,
    ) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
        backend = self._gui_backend
        method = getattr(backend, "create_session", None) if backend is not None else None
        if not callable(method):
            return None, None

        try:
            session = method(f"Sandbox {image}")
        except Exception as exc:
            return None, {
                "ok": False,
                "error": f"GUI backend create_session failed: {exc}",
                "code": "SANDBOX_BACKEND_CREATE_FAILED",
                "status_code": 502,
                "gui_backend": True,
            }

        session_id = self._backend_session_id(session)
        if session_id is None:
            return None, {
                "ok": False,
                "error": "GUI backend create_session returned an invalid session",
                "code": "SANDBOX_BACKEND_CREATE_FAILED",
                "status_code": 502,
                "gui_backend": True,
            }
        return session_id, None

    @staticmethod
    def _backend_session_id(session: Any) -> Optional[str]:
        if isinstance(session, str):
            raw_session_id: Any = session
        elif isinstance(session, dict):
            raw_session_id = session.get("session_id") or session.get("sandbox_id")
        else:
            raw_session_id = getattr(session, "session_id", None) or getattr(
                session,
                "sandbox_id",
                None,
            )
        session_id = str(raw_session_id or "").strip()
        return session_id or None

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

    def _backend_teardown(self, inst: SandboxInstance) -> Optional[str]:
        backend = self._gui_backend
        if backend is None:
            return None
        for method_name in ("destroy_session", "teardown_session", "delete_session", "destroy", "teardown"):
            method = getattr(backend, method_name, None)
            if callable(method):
                break
        else:
            return None

        try:
            result = method(inst.sandbox_id)
        except Exception as exc:
            return f"GUI backend teardown failed: {exc}"
        if isinstance(result, dict):
            if result.get("ok", True) is not True:
                return str(result.get("error") or "GUI backend teardown did not complete")
            return None
        if result is False:
            return "GUI backend teardown did not complete"
        return None

    def _backend_input_action(
        self,
        inst: SandboxInstance,
        action: str,
        success_key: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        backend = self._gui_backend
        method = getattr(backend, action, None) if backend is not None else None
        if not callable(method):
            return self._backend_unavailable(inst, action)

        try:
            result = self._call_backend_input_method(method, inst.sandbox_id, action, payload)
        except Exception as exc:
            return self._backend_action_failed(
                inst,
                action,
                f"GUI backend {action} failed: {exc}",
            )

        if not isinstance(result, dict):
            return self._backend_action_failed(
                inst,
                action,
                f"GUI backend {action} returned an invalid payload",
            )

        normalized = dict(result)
        if normalized.get("ok") is not True:
            error = str(normalized.get("error") or f"GUI backend {action} did not execute")
            normalized["ok"] = False
            normalized.setdefault("error", error)
            normalized.setdefault("code", "SANDBOX_BACKEND_ACTION_FAILED")
            normalized.setdefault("status_code", 502)
            normalized.setdefault("sandbox_id", inst.sandbox_id)
            normalized.setdefault("status", inst.status)
            normalized.setdefault("gui_backend", True)
            normalized.setdefault("action", action)
            self._strip_input_success_flags(normalized)
            return normalized

        normalized["ok"] = True
        normalized.setdefault(success_key, True)
        normalized.setdefault("sandbox_id", inst.sandbox_id)
        normalized.setdefault("status", inst.status)
        normalized.setdefault("gui_backend", True)
        normalized.setdefault("action", action)
        for key, value in payload.items():
            normalized.setdefault(key, value)
        return normalized

    def _call_backend_input_method(
        self,
        method: Callable[..., Any],
        sandbox_id: str,
        action: str,
        payload: Dict[str, Any],
    ) -> Any:
        if action == "click":
            if self._accepts_keywords(method, "x", "y"):
                return method(sandbox_id, x=payload["x"], y=payload["y"])
            return method(sandbox_id, payload["x"], payload["y"])
        if action == "type_text":
            if self._accepts_keywords(method, "text"):
                return method(sandbox_id, text=payload["text"])
            return method(sandbox_id, payload["text"])
        if action == "scroll":
            if self._accepts_keywords(method, "direction", "amount"):
                return method(
                    sandbox_id,
                    direction=payload["direction"],
                    amount=payload["amount"],
                )
            if self._accepts_keywords(method, "amount"):
                return method(sandbox_id, amount=payload["amount"])
            return method(sandbox_id, payload["amount"])
        raise ValueError(f"Unsupported sandbox input action: {action}")

    @staticmethod
    def _accepts_keywords(method: Callable[..., Any], *names: str) -> bool:
        import inspect

        try:
            signature = inspect.signature(method)
        except (TypeError, ValueError):
            return False
        parameters = signature.parameters.values()
        accepted = set()
        for parameter in parameters:
            if parameter.kind is inspect.Parameter.VAR_KEYWORD:
                return True
            accepted.add(parameter.name)
        return all(name in accepted for name in names)

    def _backend_unavailable(self, inst: SandboxInstance, action: str) -> Dict[str, Any]:
        return {
            "ok": False,
            "error": f"Sandbox input backend unavailable for {action}",
            "code": "SANDBOX_BACKEND_UNAVAILABLE",
            "status_code": 503,
            "sandbox_id": inst.sandbox_id,
            "status": inst.status,
            "gui_backend": False,
            "action": action,
        }

    def _backend_action_failed(
        self,
        inst: SandboxInstance,
        action: str,
        error: str,
    ) -> Dict[str, Any]:
        return {
            "ok": False,
            "error": error,
            "code": "SANDBOX_BACKEND_ACTION_FAILED",
            "status_code": 502,
            "sandbox_id": inst.sandbox_id,
            "status": inst.status,
            "gui_backend": True,
            "action": action,
        }

    @staticmethod
    def _strip_input_success_flags(result: Dict[str, Any]) -> None:
        for key in ("clicked", "typed", "scrolled", "recorded"):
            result.pop(key, None)

    def _touch_ready_instance(self, sandbox_id: str) -> None:
        with self._lock:
            inst = self._instances.get(str(sandbox_id))
            if inst is None or inst.status not in RUNNING_STATUSES:
                return
            inst.touch()
            self._save_registry()


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


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple, set)):
        return ()
    return tuple(str(item) for item in value if str(item))


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
