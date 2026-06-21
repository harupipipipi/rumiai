from __future__ import annotations

import json
import os
import platform
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .errors import RUNTIME_PROVIDER_UNAVAILABLE, SandboxContractError
from .models import (
    DesktopSpec,
    FilesystemPolicy,
    LifecyclePolicy,
    NetworkPolicy,
    ProviderInstance,
    ResolvedSandboxTemplate,
    ResourceLimits,
    SandboxCreateSpec,
    SandboxInstance,
    RuntimeRequirements,
    SecretsPolicy,
    WorkspaceBinding,
    model_to_dict,
)
from .provider_registry import ProviderRegistry


REGISTRY_SCHEMA_VERSION = 3
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
LEGACY_PLACEHOLDER_PROVIDER = "legacy_placeholder"
VALID_STATES = {
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
}
RUNNING_STATES = {READY, BUSY}
TERMINAL_STATES = {DESTROYED, FAILED}
SUPPORTED_MODEL_MODES = {"fast", "heavy"}
STATE_DIR_ENV = "RUMI_DEFAULTSPACK_SANDBOX_STATE_DIR"


class SandboxManager:
    def __init__(
        self,
        state_dir: str | Path | None = None,
        *,
        registry_path: str | Path | None = None,
        gui_backend: Any | None = None,
        provider_registry: ProviderRegistry | None = None,
    ) -> None:
        self.state_dir = Path(state_dir) if state_dir is not None else self._default_state_dir()
        self.registry_path = (
            Path(registry_path) if registry_path is not None else self.state_dir / "sandboxes.json"
        )
        # GUI backend injection is intentionally test-only until a managed provider
        # owns desktop capture/input in production.
        self._gui_backend = gui_backend
        self._provider_registry = provider_registry or ProviderRegistry()
        self._lock = threading.RLock()
        self._instances: Dict[str, SandboxInstance] = {}
        self._model_mode: str = "fast"
        self._load_registry()

    def create(
        self,
        image: str = "ubuntu:22.04",
        display: bool = True,
        *,
        provider_id: str | None = None,
    ) -> Dict[str, Any]:
        image = str(image or "").strip() or "ubuntu:22.04"
        display = bool(display)
        template = self._template_for_create(image=image, display=display)
        requirements = RuntimeRequirements(
            template_id=template.template_id,
            required_capabilities=template.provider_requirements,
            provider_id=provider_id,
        )
        try:
            provider = self._provider_registry.resolve(provider_id or "auto", requirements)
            provider_instance = provider.create(
                SandboxCreateSpec(
                    name=f"Sandbox {image}",
                    template=template,
                    provider_id=provider.provider_id,
                    metadata={"image": image, "display": display},
                )
            )
            started = provider.start(provider_instance)
        except SandboxContractError as exc:
            return exc.to_dict()
        except Exception as exc:
            return {
                "ok": False,
                "error": f"Managed runtime provider failed to create sandbox: {exc}",
                "code": RUNTIME_PROVIDER_UNAVAILABLE,
                "status_code": 503,
            }

        with self._lock:
            now = time.time()
            inst = SandboxInstance(
                sandbox_id=started.sandbox_id,
                name=f"Sandbox {image}",
                image=image,
                display=display,
                template_id=template.template_id,
                template_version=template.template_version,
                provider_id=started.provider_id,
                provider_instance_id=started.provider_instance_id,
                runtime_id=started.runtime_id,
                state=_canonical_state(started.state),
                created_at=now,
                updated_at=now,
                started_at=now if _canonical_state(started.state) in RUNNING_STATES else None,
                capabilities=template.provider_requirements,
                resource_limits=template.resources,
                workspace_binding=WorkspaceBinding(),
                network_policy=template.network,
                desktop_spec=template.desktop,
                generation=max(1, int(started.generation or 1)),
            )
            self._instances[inst.sandbox_id] = inst
            self._save_registry()
            return {
                "ok": True,
                "created": True,
                "sandbox_id": inst.sandbox_id,
                "status": inst.state,
                "state": inst.state,
                "template_id": inst.template_id,
                "provider_id": inst.provider_id,
                "registry_path": str(self.registry_path),
            }

    def destroy(self, sandbox_id: str) -> Dict[str, Any]:
        with self._lock:
            inst = self._instances.get(str(sandbox_id))
            if inst is None:
                return self._not_found(sandbox_id)
            if inst.state == DESTROYED:
                return {
                    "ok": True,
                    "destroyed": True,
                    "sandbox_id": inst.sandbox_id,
                    "status": inst.state,
                    "state": inst.state,
                }

        teardown_error = self._backend_teardown(inst)
        if teardown_error is not None:
            return self._mark_failed(inst.sandbox_id, teardown_error, code="SANDBOX_BACKEND_DESTROY_FAILED")

        provider_error = self._provider_destroy(inst)
        if provider_error is not None:
            return self._mark_failed(inst.sandbox_id, provider_error, code="SANDBOX_PROVIDER_DESTROY_FAILED")

        with self._lock:
            inst = self._instances.get(str(sandbox_id))
            if inst is None:
                return self._not_found(sandbox_id)
            if inst.state != DESTROYED:
                now = time.time()
                inst.state = DESTROYED
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
                "status": inst.state,
                "state": inst.state,
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

        return self._backend_unavailable(inst, "screenshot")

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
            return {"ok": True, **self._instance_to_dict(inst)}

    def list_instances(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [self._instance_to_dict(instance) for instance in self._instances.values()]

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
                inst = self._instance_from_dict(raw, legacy=schema_version < REGISTRY_SCHEMA_VERSION)
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
                sandbox_id: self._instance_to_dict(inst)
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
        if inst.state in TERMINAL_STATES:
            return None, {
                "ok": False,
                "error": f"Sandbox is {inst.state}: {sandbox_id}",
                "code": "SANDBOX_NOT_RUNNING",
                "status_code": 409,
                "sandbox_id": str(sandbox_id),
                "status": inst.state,
                "state": inst.state,
            }
        if inst.state not in RUNNING_STATES:
            return None, {
                "ok": False,
                "error": f"Sandbox is not running ({inst.state}): {sandbox_id}",
                "code": "SANDBOX_NOT_RUNNING",
                "status_code": 409,
                "sandbox_id": str(sandbox_id),
                "status": inst.state,
                "state": inst.state,
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

    def _mark_failed(self, sandbox_id: str, message: str, *, code: str) -> Dict[str, Any]:
        with self._lock:
            inst = self._instances.get(str(sandbox_id))
            if inst is not None and inst.state != DESTROYED:
                now = time.time()
                inst.state = FAILED
                inst.updated_at = now
                inst.last_activity_at = now
                inst.last_error = message
                self._save_registry()
        return {
            "ok": False,
            "destroyed": False,
            "sandbox_id": str(sandbox_id),
            "status": FAILED,
            "state": FAILED,
            "error": message,
            "code": code,
            "status_code": 502,
            "gui_backend": code == "SANDBOX_BACKEND_DESTROY_FAILED",
        }

    def _provider_destroy(self, inst: SandboxInstance) -> Optional[str]:
        if inst.provider_id == LEGACY_PLACEHOLDER_PROVIDER:
            return None
        try:
            provider = self._provider_registry.get(inst.provider_id)
            provider.destroy(self._provider_instance(inst))
        except SandboxContractError as exc:
            return exc.message
        except Exception as exc:
            return f"Managed runtime provider destroy failed: {exc}"
        return None

    def _provider_instance(self, inst: SandboxInstance) -> ProviderInstance:
        return ProviderInstance(
            provider_id=inst.provider_id,
            provider_instance_id=inst.provider_instance_id,
            sandbox_id=inst.sandbox_id,
            runtime_id=inst.runtime_id,
            state=inst.state,
            opaque_state={"template_id": inst.template_id},
            generation=inst.generation,
        )

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
                "status": inst.state,
                "state": inst.state,
            }
        if not isinstance(result, dict):
            return {
                "ok": False,
                "error": "GUI backend screenshot returned an invalid payload",
                "code": "SANDBOX_SCREENSHOT_FAILED",
                "status_code": 502,
                "sandbox_id": inst.sandbox_id,
                "status": inst.state,
                "state": inst.state,
            }
        result.setdefault("ok", True)
        result.setdefault("sandbox_id", inst.sandbox_id)
        result.setdefault("status", inst.state)
        result.setdefault("state", inst.state)
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
            normalized.setdefault("status", inst.state)
            normalized.setdefault("state", inst.state)
            normalized.setdefault("gui_backend", True)
            normalized.setdefault("action", action)
            self._strip_input_success_flags(normalized)
            return normalized

        normalized["ok"] = True
        normalized.setdefault(success_key, True)
        normalized.setdefault("sandbox_id", inst.sandbox_id)
        normalized.setdefault("status", inst.state)
        normalized.setdefault("state", inst.state)
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
            "error": f"Sandbox backend unavailable for {action}",
            "code": "SANDBOX_BACKEND_UNAVAILABLE",
            "status_code": 503,
            "sandbox_id": inst.sandbox_id,
            "status": inst.state,
            "state": inst.state,
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
            "status": inst.state,
            "state": inst.state,
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
            if inst is None or inst.state not in RUNNING_STATES:
                return
            inst.touch()
            self._save_registry()

    def _template_for_create(self, *, image: str, display: bool) -> ResolvedSandboxTemplate:
        capabilities = {"sandbox.exec", "sandbox.files"}
        allowed_operations = {"exec", "files.read", "files.write"}
        desktop = None
        template_id = "tool.ephemeral"
        if display:
            capabilities.update({"sandbox.desktop", "sandbox.desktop_input"})
            allowed_operations.add("desktop.input")
            desktop = DesktopSpec(enabled=True, width=1440, height=900, display_backend="x11")
            template_id = "desktop.ubuntu"
        return ResolvedSandboxTemplate(
            template_id=template_id,
            template_version="1",
            runtime_os="linux",
            provider_requirements=frozenset(capabilities),
            packages=(),
            desktop=desktop,
            filesystem=FilesystemPolicy(mode="ephemeral_overlay", workspace_access="none"),
            network=NetworkPolicy(mode="off"),
            secrets=SecretsPolicy(mode="denied"),
            resources=ResourceLimits(cpu_count=1, memory_mb=2048, timeout_ms=600_000),
            lifecycle=LifecyclePolicy(ttl_seconds=900, persistent=False, destroy_on_exit=True),
            allowed_operations=frozenset(allowed_operations),
            source_template_ids=(template_id, image),
        )

    def _instance_to_dict(self, inst: SandboxInstance) -> Dict[str, Any]:
        payload = model_to_dict(inst)
        payload["status"] = inst.state
        payload["state"] = inst.state
        return payload

    def _instance_from_dict(self, data: Dict[str, Any], *, legacy: bool = False) -> SandboxInstance:
        raw_state = data.get("state", data.get("status", READY))
        state = _canonical_state(raw_state)
        provider_id = str(data.get("provider_id") or "")
        provider_instance_id = str(data.get("provider_instance_id") or "")
        last_error = str(data.get("last_error")) if data.get("last_error") is not None else None
        stopped_at = _optional_float(data.get("stopped_at"))
        if legacy and state == READY and not provider_instance_id:
            state = STOPPED
            provider_id = LEGACY_PLACEHOLDER_PROVIDER
            stopped_at = _optional_float(data.get("updated_at")) or _optional_float(data.get("created_at"))
            last_error = "Migrated prototype sandbox; old fake-ready instances are not treated as live."
        display = bool(data.get("display", True))
        return SandboxInstance(
            sandbox_id=str(data.get("sandbox_id") or ""),
            name=str(data.get("name") or ""),
            image=str(data.get("image") or "ubuntu:22.04"),
            display=display,
            template_id=str(data.get("template_id") or ("desktop.ubuntu" if display else "tool.ephemeral")),
            template_version=str(data.get("template_version") or "compat"),
            provider_id=provider_id,
            provider_instance_id=provider_instance_id,
            runtime_id=str(data.get("runtime_id") or ""),
            state=state,
            created_at=_float_or_now(data.get("created_at")),
            updated_at=_float_or_now(data.get("updated_at")),
            started_at=_optional_float(data.get("started_at")),
            stopped_at=stopped_at,
            destroyed_at=_optional_float(data.get("destroyed_at")),
            last_activity_at=_optional_float(data.get("last_activity_at")),
            last_error=last_error,
            capabilities=frozenset(_string_tuple(data.get("capabilities"))),
            resource_limits=ResourceLimits(),
            workspace_binding=WorkspaceBinding(),
            network_policy=NetworkPolicy(),
            desktop_spec=DesktopSpec(enabled=True) if display else None,
            generation=max(1, int(_float_or_zero(data.get("generation") or 1))),
            recovery_token_hash=str(data.get("recovery_token_hash")) if data.get("recovery_token_hash") is not None else None,
        )


def _canonical_state(value: Any) -> str:
    state = str(value or READY).strip().lower()
    if state == "error":
        return FAILED
    return state if state in VALID_STATES else FAILED


def _float_or_zero(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _float_or_now(value: Any) -> float:
    parsed = _float_or_zero(value)
    return parsed or time.time()


def _optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple, set, frozenset)):
        return ()
    return tuple(str(item) for item in value if str(item))
