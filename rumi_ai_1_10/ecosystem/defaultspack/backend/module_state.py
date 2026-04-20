from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[3]
DEFAULT_PACK_ROOT = BASE_DIR / "ecosystem" / "defaultspack"
DEFAULT_STATE_FILE = (
    BASE_DIR / "user_data" / "packs" / "defaultspack" / "module_state.json"
)


class ModuleState(str, Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"
    DEGRADED = "degraded"
    ERROR_DISABLED = "error_disabled"
    EXPERIMENTAL = "experimental"


MODULE_STATES = frozenset(state.value for state in ModuleState)
STATE_EVENT_NAMES = {
    "enabled": "module.enabled",
    "disabled": "module.disabled",
    "degraded": "module.degraded",
    "error_disabled": "module.error_disabled",
    "experimental": "module.enabled",
}


@dataclass(frozen=True)
class ModuleSpec:
    module_id: str
    kind: str
    display_name: str
    description: str
    dependencies: List[str] = field(default_factory=list)
    default_state: str = "enabled"
    failure_threshold: int = 3
    experimental: bool = False
    source_path: str = ""


@dataclass
class ModuleHealth:
    module_id: str
    kind: str = "backend"
    state: ModuleState = ModuleState.DISABLED
    failure_count: int = 0
    failure_threshold: int = 3
    dependencies: List[str] = field(default_factory=list)
    display_name: str = ""
    description: str = ""
    last_error: Optional[str] = None
    updated_at: str = ""
    experimental: bool = False
    source_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "module_id": self.module_id,
            "kind": self.kind,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "dependencies": list(self.dependencies),
            "display_name": self.display_name,
            "description": self.description,
            "last_error": self.last_error,
            "updated_at": self.updated_at,
            "experimental": self.experimental,
            "source_path": self.source_path,
        }


class ModuleStateManager:
    def __init__(
        self,
        event_bus: Any = None,
        pack_root: Path | None = None,
        state_file: Path | None = None,
    ) -> None:
        self._event_bus = event_bus
        self.pack_root = Path(pack_root or DEFAULT_PACK_ROOT)
        self.state_file = Path(state_file or DEFAULT_STATE_FILE)
        self._lock = RLock()
        self._modules: Dict[str, ModuleHealth] = {}

    @staticmethod
    def _now_ts() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _module_files(self) -> Iterable[Path]:
        for area in ("backend", "frontend"):
            base = self.pack_root / area
            if not base.is_dir():
                continue
            for candidate in sorted(base.glob("*/module.json")):
                if candidate.is_file():
                    yield candidate

    def _load_specs(self) -> Dict[str, ModuleSpec]:
        specs: Dict[str, ModuleSpec] = {}
        for module_file in self._module_files():
            try:
                raw = json.loads(module_file.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("Failed to parse module file %s: %s", module_file, exc)
                continue
            module_id = str(raw.get("module_id") or module_file.parent.name)
            default_state = str(raw.get("default_state", "enabled"))
            if default_state not in MODULE_STATES:
                default_state = "enabled"
            spec = ModuleSpec(
                module_id=module_id,
                kind=str(raw.get("kind", module_file.parent.parent.name)),
                display_name=str(raw.get("display_name", module_id)),
                description=str(raw.get("description", "")),
                dependencies=[
                    str(item) for item in raw.get("dependencies", [])
                    if isinstance(item, str) and item.strip()
                ],
                default_state=default_state,
                failure_threshold=max(1, int(raw.get("failure_threshold", 3))),
                experimental=bool(raw.get("experimental", False)),
                source_path=str(module_file.parent.resolve()),
            )
            specs[module_id] = spec
        return specs

    def _load_state_data(self) -> Dict[str, Dict[str, Any]]:
        if not self.state_file.is_file():
            return {}
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to parse module state file %s: %s", self.state_file, exc)
            return {}
        modules = data.get("modules", {})
        return modules if isinstance(modules, dict) else {}

    def _save_state_data(self, modules: Dict[str, ModuleHealth]) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": "1.0",
            "updated_at": self._now_ts(),
            "modules": {mid: module.to_dict() for mid, module in modules.items()},
        }
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.state_file)

    def _load_catalog_modules(self) -> Dict[str, ModuleHealth]:
        specs = self._load_specs()
        persisted = self._load_state_data()
        modules: Dict[str, ModuleHealth] = {}
        now = self._now_ts()
        for module_id, spec in specs.items():
            raw = persisted.get(module_id, {})
            state = spec.default_state
            failure_count = 0
            last_error = None
            updated_at = now
            if isinstance(raw, dict):
                raw_state = str(raw.get("state", state))
                if raw_state in MODULE_STATES:
                    state = raw_state
                failure_count = max(0, int(raw.get("failure_count", 0) or 0))
                last_error = raw.get("last_error")
                updated_at = str(raw.get("updated_at") or now)
            if spec.experimental and state == "enabled":
                state = "experimental"
            modules[module_id] = ModuleHealth(
                module_id=module_id,
                kind=spec.kind,
                state=ModuleState(state),
                failure_count=failure_count,
                failure_threshold=spec.failure_threshold,
                dependencies=list(spec.dependencies),
                display_name=spec.display_name,
                description=spec.description,
                last_error=str(last_error) if last_error else None,
                updated_at=updated_at,
                experimental=spec.experimental,
                source_path=spec.source_path,
            )
        self._apply_dependency_health(modules)
        return modules

    def _ensure_catalog_loaded(self) -> None:
        if self._modules:
            return
        self._modules = self._load_catalog_modules()

    def register_module(
        self,
        module_id: str,
        kind: str = "backend",
        display_name: str = "",
        description: str = "",
        dependencies: Optional[List[str]] = None,
        default_state: str = "enabled",
        failure_threshold: int = 3,
    ) -> ModuleHealth:
        with self._lock:
            state = ModuleState(default_state) if default_state in MODULE_STATES else ModuleState.DISABLED
            health = ModuleHealth(
                module_id=module_id,
                kind=kind,
                state=state,
                failure_threshold=max(1, int(failure_threshold)),
                dependencies=list(dependencies or []),
                display_name=display_name,
                description=description,
                updated_at=self._now_ts(),
            )
            self._modules[module_id] = health
            self._apply_dependency_health(self._modules)
            return health

    def _emit(self, topic: str, payload: Dict[str, Any]) -> None:
        if self._event_bus is None:
            return
        try:
            self._event_bus.publish(topic, payload)
        except Exception:
            logger.debug("Failed to emit module event", exc_info=True)

    def _apply_dependency_health(self, modules: Dict[str, ModuleHealth]) -> None:
        for module in modules.values():
            if module.state in {ModuleState.DISABLED, ModuleState.ERROR_DISABLED}:
                continue
            broken = [
                dep for dep in module.dependencies
                if dep not in modules
                or modules[dep].state in {ModuleState.DISABLED, ModuleState.ERROR_DISABLED}
            ]
            if broken:
                module.state = ModuleState.DEGRADED
                module.last_error = "dependency_unavailable:" + ",".join(sorted(broken))

    def get(self, module_id: str) -> Optional[ModuleHealth]:
        with self._lock:
            self._ensure_catalog_loaded()
            return self._modules.get(module_id)

    def get_state(self, module_id: str) -> ModuleState:
        module = self.get(module_id)
        return module.state if module else ModuleState.DISABLED

    def list_modules(self) -> List[Dict[str, Any]]:
        with self._lock:
            self._ensure_catalog_loaded()
            return [module.to_dict() for module in self._modules.values()]

    def get_impact_map(self) -> Dict[str, List[str]]:
        with self._lock:
            self._ensure_catalog_loaded()
            impact: Dict[str, List[str]] = {mid: [] for mid in self._modules}
            for module in self._modules.values():
                for dep in module.dependencies:
                    impact.setdefault(dep, []).append(module.module_id)
            return impact

    def get_catalog(self) -> Dict[str, Any]:
        with self._lock:
            self._modules = self._load_catalog_modules()
            self._save_state_data(self._modules)
            entries = [self._modules[mid].to_dict() for mid in sorted(self._modules)]
            return {
                "pack_id": "defaultspack",
                "modules": entries,
                "count": len(entries),
                "dependency_graph": {
                    item["module_id"]: list(item["dependencies"]) for item in entries
                },
                "impacts": self.get_impact_map(),
            }

    def get_module(self, module_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            self._modules = self._load_catalog_modules()
            self._save_state_data(self._modules)
            module = self._modules.get(module_id)
            return module.to_dict() if module else None

    def set_state(self, module_id: str, state: str, reason: str = "") -> Dict[str, Any]:
        with self._lock:
            loaded = self._load_catalog_modules() if not self._modules else {}
            if loaded:
                self._modules = loaded
            module = self._modules.get(module_id)
            if module is None:
                return {"error": f"Unknown module: {module_id}", "status_code": 404}
            if state not in MODULE_STATES:
                return {"error": f"Unsupported module state: {state}", "status_code": 400}
            module.state = ModuleState(state)
            module.updated_at = self._now_ts()
            if state in {"enabled", "experimental"}:
                module.failure_count = 0
                module.last_error = None
            elif reason:
                module.last_error = reason
            self._apply_dependency_health(self._modules)
            self._save_state_data(self._modules)
            event_name = STATE_EVENT_NAMES.get(module.state.value, f"module.{state}")
            self._emit(event_name, {"module_id": module_id, "state": module.state.value, "reason": reason})
            if module.state == ModuleState.ENABLED:
                self._emit("module.recovered", {"module_id": module_id, "state": module.state.value, "reason": reason})
            return {"module_id": module_id, "state": module.state.value, "updated": True}

    def enable(self, module_id: str) -> Dict[str, Any]:
        return self.set_state(module_id, ModuleState.ENABLED.value)

    def disable(self, module_id: str, reason: str = "manual_disable") -> Dict[str, Any]:
        return self.set_state(module_id, ModuleState.DISABLED.value, reason=reason)

    def reload(self, module_id: str) -> Dict[str, Any]:
        return self.set_state(module_id, ModuleState.ENABLED.value, reason="manual_reload")

    def rollback(self, module_id: str) -> Dict[str, Any]:
        return self.set_state(module_id, ModuleState.DISABLED.value, reason="manual_rollback")

    def recover(self, module_id: str) -> Dict[str, Any]:
        return self.set_state(module_id, ModuleState.ENABLED.value, reason="manual_recover")

    def record_failure(self, module_id: str, error: str) -> Dict[str, Any]:
        with self._lock:
            if not self._modules:
                self._modules = self._load_catalog_modules()
            module = self._modules.get(module_id)
            if module is None:
                return {"error": f"Unknown module: {module_id}", "status_code": 404}
            module.failure_count += 1
            module.last_error = error
            module.updated_at = self._now_ts()
            if module.failure_count >= module.failure_threshold:
                module.state = ModuleState.ERROR_DISABLED
            else:
                module.state = ModuleState.DEGRADED
            self._apply_dependency_health(self._modules)
            self._save_state_data(self._modules)
            self._emit(f"module.{module.state.value}", {"module_id": module_id, "state": module.state.value, "reason": error})
            return {"module_id": module_id, "state": module.state.value, "failure_count": module.failure_count}


_global_module_state_manager: ModuleStateManager | None = None


def get_module_state_manager(event_bus: Any = None) -> ModuleStateManager:
    global _global_module_state_manager
    if _global_module_state_manager is None:
        _global_module_state_manager = ModuleStateManager(event_bus=event_bus)
    elif event_bus is not None and _global_module_state_manager._event_bus is None:
        _global_module_state_manager._event_bus = event_bus
    return _global_module_state_manager
