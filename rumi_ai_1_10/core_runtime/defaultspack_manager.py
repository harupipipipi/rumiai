"""
defaultspack_manager.py - defaultspack module catalog / state manager

The new defaultspack pack is intentionally modular. This manager scans the
tracked pack layout, persists per-module state, and emits standard health
events through EventBus.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .paths import BASE_DIR

logger = logging.getLogger(__name__)

MODULE_STATES = frozenset({
    "enabled",
    "disabled",
    "degraded",
    "error_disabled",
    "experimental",
})
STATE_EVENT_NAMES = {
    "enabled": "module.enabled",
    "disabled": "module.disabled",
    "degraded": "module.degraded",
    "error_disabled": "module.error_disabled",
    "experimental": "module.enabled",
}
DEFAULTSPACK_ROOT = BASE_DIR / "ecosystem" / "defaultspack"
DEFAULTSPACK_STATE_FILE = (
    BASE_DIR / "user_data" / "settings" / "defaultspack_modules.json"
)


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
class ModuleStateRecord:
    module_id: str
    state: str
    failure_count: int = 0
    last_error: Optional[str] = None
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "module_id": self.module_id,
            "state": self.state,
            "failure_count": self.failure_count,
            "last_error": self.last_error,
            "updated_at": self.updated_at,
        }


class DefaultspackManager:
    def __init__(
        self,
        pack_root: Path | None = None,
        state_file: Path | None = None,
        event_bus: Any = None,
    ) -> None:
        self.pack_root = Path(pack_root or DEFAULTSPACK_ROOT)
        self.state_file = Path(state_file or DEFAULTSPACK_STATE_FILE)
        self.event_bus = event_bus

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
                logger.warning(
                    "Failed to parse defaultspack module file %s: %s",
                    module_file,
                    exc,
                )
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
            logger.warning(
                "Failed to parse defaultspack state file %s: %s",
                self.state_file,
                exc,
            )
            return {}
        modules = data.get("modules", {})
        return modules if isinstance(modules, dict) else {}

    def _save_state_data(self, modules: Dict[str, ModuleStateRecord]) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": "1.0",
            "updated_at": self._now_ts(),
            "modules": {mid: record.to_dict() for mid, record in modules.items()},
        }
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.state_file)

    def _load_records(self, specs: Dict[str, ModuleSpec]) -> Dict[str, ModuleStateRecord]:
        persisted = self._load_state_data()
        records: Dict[str, ModuleStateRecord] = {}
        now = self._now_ts()
        for module_id, spec in specs.items():
            state = spec.default_state
            failure_count = 0
            last_error = None
            updated_at = now
            raw = persisted.get(module_id, {})
            if isinstance(raw, dict):
                persisted_state = str(raw.get("state", state))
                if persisted_state in MODULE_STATES:
                    state = persisted_state
                failure_count = int(raw.get("failure_count", 0) or 0)
                last_error = raw.get("last_error")
                updated_at = str(raw.get("updated_at") or now)
            if spec.experimental and state == "enabled":
                state = "experimental"
            records[module_id] = ModuleStateRecord(
                module_id=module_id,
                state=state,
                failure_count=max(0, failure_count),
                last_error=str(last_error) if last_error else None,
                updated_at=updated_at,
            )
        self._repair_dependency_states(specs, records)
        return records

    def _emit_state_event(
        self,
        module_id: str,
        state: str,
        reason: str = "",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        if self.event_bus is None:
            return
        event_name = STATE_EVENT_NAMES.get(state)
        if not event_name:
            return
        payload = {
            "module_id": module_id,
            "state": state,
            "reason": reason,
            "ts": self._now_ts(),
        }
        if details:
            payload.update(details)
        try:
            self.event_bus.publish(event_name, payload)
        except Exception:
            logger.debug("Failed to emit event %s for %s", event_name, module_id, exc_info=True)

    def _repair_dependency_states(
        self,
        specs: Dict[str, ModuleSpec],
        records: Dict[str, ModuleStateRecord],
    ) -> None:
        for module_id, spec in specs.items():
            record = records[module_id]
            if record.state in {"disabled", "error_disabled"}:
                continue
            missing_or_disabled = [
                dep for dep in spec.dependencies
                if dep not in records or records[dep].state in {"disabled", "error_disabled"}
            ]
            if missing_or_disabled:
                record.state = "degraded"
                record.last_error = (
                    "dependency_unavailable:" + ",".join(sorted(missing_or_disabled))
                )

    def _catalog_entries(self) -> List[Dict[str, Any]]:
        specs = self._load_specs()
        records = self._load_records(specs)
        self._save_state_data(records)
        entries: List[Dict[str, Any]] = []
        for module_id in sorted(specs):
            spec = specs[module_id]
            record = records[module_id]
            entries.append({
                "module_id": module_id,
                "kind": spec.kind,
                "display_name": spec.display_name,
                "description": spec.description,
                "dependencies": list(spec.dependencies),
                "state": record.state,
                "failure_count": record.failure_count,
                "failure_threshold": spec.failure_threshold,
                "last_error": record.last_error,
                "experimental": spec.experimental,
                "source_path": spec.source_path,
                "updated_at": record.updated_at,
            })
        return entries

    def get_catalog(self) -> Dict[str, Any]:
        entries = self._catalog_entries()
        impacts = {
            item["module_id"]: [
                other["module_id"]
                for other in entries
                if item["module_id"] in other["dependencies"]
            ]
            for item in entries
        }
        return {
            "pack_id": "defaultspack",
            "modules": entries,
            "count": len(entries),
            "dependency_graph": {
                item["module_id"]: list(item["dependencies"]) for item in entries
            },
            "impacts": impacts,
        }

    def get_module(self, module_id: str) -> Optional[Dict[str, Any]]:
        for item in self._catalog_entries():
            if item["module_id"] == module_id:
                return item
        return None

    def set_state(
        self,
        module_id: str,
        state: str,
        reason: str = "",
    ) -> Dict[str, Any]:
        if state not in MODULE_STATES:
            return {"error": f"Unsupported module state: {state}", "status_code": 400}
        specs = self._load_specs()
        if module_id not in specs:
            return {"error": f"Unknown module: {module_id}", "status_code": 404}
        records = self._load_records(specs)
        record = records[module_id]
        if state in {"enabled", "experimental"}:
            record.failure_count = 0
            record.last_error = None
        record.state = state
        record.updated_at = self._now_ts()
        if reason:
            record.last_error = reason if state in {"degraded", "error_disabled"} else None
        self._repair_dependency_states(specs, records)
        self._save_state_data(records)
        self._emit_state_event(module_id, record.state, reason=reason)
        return {"module_id": module_id, "state": record.state, "updated": True}

    def enable(self, module_id: str) -> Dict[str, Any]:
        return self.set_state(module_id, "enabled")

    def disable(self, module_id: str, reason: str = "manual_disable") -> Dict[str, Any]:
        return self.set_state(module_id, "disabled", reason=reason)

    def reload(self, module_id: str) -> Dict[str, Any]:
        return self.set_state(module_id, "enabled", reason="manual_reload")

    def rollback(self, module_id: str) -> Dict[str, Any]:
        return self.set_state(module_id, "disabled", reason="manual_rollback")

    def record_failure(self, module_id: str, error: str) -> Dict[str, Any]:
        specs = self._load_specs()
        if module_id not in specs:
            return {"error": f"Unknown module: {module_id}", "status_code": 404}
        records = self._load_records(specs)
        record = records[module_id]
        record.failure_count += 1
        record.last_error = error
        record.updated_at = self._now_ts()
        if record.failure_count >= specs[module_id].failure_threshold:
            record.state = "error_disabled"
        else:
            record.state = "degraded"
        self._repair_dependency_states(specs, records)
        self._save_state_data(records)
        self._emit_state_event(module_id, record.state, reason=error)
        return {
            "module_id": module_id,
            "state": record.state,
            "failure_count": record.failure_count,
        }

    def recover(self, module_id: str) -> Dict[str, Any]:
        result = self.set_state(module_id, "enabled", reason="manual_recover")
        if "error" not in result and self.event_bus is not None:
            try:
                self.event_bus.publish(
                    "module.recovered",
                    {"module_id": module_id, "state": "enabled", "ts": self._now_ts()},
                )
            except Exception:
                logger.debug("Failed to emit module.recovered", exc_info=True)
        return result


_global_defaultspack_manager: DefaultspackManager | None = None


def get_defaultspack_manager(event_bus: Any = None) -> DefaultspackManager:
    global _global_defaultspack_manager
    if _global_defaultspack_manager is None:
        _global_defaultspack_manager = DefaultspackManager(event_bus=event_bus)
    elif event_bus is not None and _global_defaultspack_manager.event_bus is None:
        _global_defaultspack_manager.event_bus = event_bus
    return _global_defaultspack_manager
