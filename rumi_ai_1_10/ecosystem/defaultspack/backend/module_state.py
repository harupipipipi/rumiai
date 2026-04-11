from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from threading import RLock
from typing import Any, Dict, List, Optional


class ModuleState(str, Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"
    DEGRADED = "degraded"
    ERROR_DISABLED = "error_disabled"
    EXPERIMENTAL = "experimental"


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


class ModuleStateManager:
    def __init__(self, event_bus: Any = None) -> None:
        self._event_bus = event_bus
        self._lock = RLock()
        self._modules: Dict[str, ModuleHealth] = {}

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
            state = ModuleState(default_state) if default_state in ModuleState._value2member_map_ else ModuleState.DISABLED
            if state == ModuleState.EXPERIMENTAL:
                state = ModuleState.EXPERIMENTAL
            health = ModuleHealth(
                module_id=module_id,
                kind=kind,
                state=state,
                failure_threshold=max(1, int(failure_threshold)),
                dependencies=list(dependencies or []),
                display_name=display_name,
                description=description,
            )
            self._modules[module_id] = health
            self._apply_dependency_health()
            return health

    def _emit(self, topic: str, payload: Dict[str, Any]) -> None:
        if self._event_bus is None:
            return
        try:
            self._event_bus.publish(topic, payload)
        except Exception:
            pass

    def _apply_dependency_health(self) -> None:
        for module in self._modules.values():
            if module.state in {ModuleState.DISABLED, ModuleState.ERROR_DISABLED}:
                continue
            broken = [dep for dep in module.dependencies if dep not in self._modules or self._modules[dep].state in {ModuleState.DISABLED, ModuleState.ERROR_DISABLED}]
            if broken:
                module.state = ModuleState.DEGRADED
                module.last_error = "dependency_unavailable:" + ",".join(sorted(broken))

    def get(self, module_id: str) -> Optional[ModuleHealth]:
        with self._lock:
            return self._modules.get(module_id)

    def get_state(self, module_id: str) -> ModuleState:
        module = self.get(module_id)
        return module.state if module else ModuleState.DISABLED

    def list_modules(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [self._to_dict(module) for module in self._modules.values()]

    def _to_dict(self, module: ModuleHealth) -> Dict[str, Any]:
        return {
            "module_id": module.module_id,
            "kind": module.kind,
            "state": module.state.value,
            "failure_count": module.failure_count,
            "failure_threshold": module.failure_threshold,
            "dependencies": list(module.dependencies),
            "display_name": module.display_name,
            "description": module.description,
            "last_error": module.last_error,
        }

    def get_impact_map(self) -> Dict[str, List[str]]:
        with self._lock:
            impact: Dict[str, List[str]] = {mid: [] for mid in self._modules}
            for module in self._modules.values():
                for dep in module.dependencies:
                    impact.setdefault(dep, []).append(module.module_id)
            return impact

    def set_state(self, module_id: str, state: str, reason: str = "") -> Dict[str, Any]:
        with self._lock:
            module = self._modules.get(module_id)
            if module is None:
                return {"error": f"Unknown module: {module_id}", "status_code": 404}
            if state not in ModuleState._value2member_map_:
                return {"error": f"Unsupported module state: {state}", "status_code": 400}
            module.state = ModuleState(state)
            if state in {"enabled", "experimental"}:
                module.failure_count = 0
                module.last_error = None
            elif reason:
                module.last_error = reason
            self._apply_dependency_health()
            event_name = f"module.{state}"
            self._emit(event_name, {"module_id": module_id, "state": state, "reason": reason})
            if state == "enabled":
                self._emit("module.recovered", {"module_id": module_id, "state": state, "reason": reason})
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
            module = self._modules.get(module_id)
            if module is None:
                return {"error": f"Unknown module: {module_id}", "status_code": 404}
            module.failure_count += 1
            module.last_error = error
            if module.failure_count >= module.failure_threshold:
                module.state = ModuleState.ERROR_DISABLED
            else:
                module.state = ModuleState.DEGRADED
            self._apply_dependency_health()
            self._emit(f"module.{module.state.value}", {"module_id": module_id, "state": module.state.value, "reason": error})
            return {"module_id": module_id, "state": module.state.value, "failure_count": module.failure_count}
