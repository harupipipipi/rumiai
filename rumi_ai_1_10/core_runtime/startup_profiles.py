from __future__ import annotations

import copy
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .paths import discover_pack_locations

logger = logging.getLogger(__name__)

START_CONTRACT = "rumiai.start.standard.v1"

SLOT_SPECS: List[Dict[str, Any]] = [
    {
        "slot_id": "tool",
        "label": "Tool",
        "description": "Tool invocation and consent surface.",
        "contract": "rumiai.slot.tool.v1",
        "multi": False,
        "required_provides": ["defaults.tool.invoke"],
        "component_types": ["tool"],
        "interface_key": "rumiai.slot.tool",
        "character": "T",
    },
    {
        "slot_id": "frontend",
        "label": "Frontend",
        "description": "Viewer, transport, and event surface.",
        "contract": "rumiai.slot.frontend.v1",
        "multi": False,
        "required_provides": ["defaults.frontend.start"],
        "component_types": ["frontend"],
        "interface_key": "rumiai.slot.frontend",
        "extra_interface_keys": ["io.http.server"],
        "character": "F",
    },
    {
        "slot_id": "ai_client",
        "label": "AI Client",
        "description": "Completion and model routing surface.",
        "contract": "rumiai.slot.ai_client.v1",
        "multi": False,
        "required_provides": ["defaults.ai.complete"],
        "component_types": ["ai_client"],
        "interface_key": "rumiai.slot.ai_client",
        "character": "A",
    },
    {
        "slot_id": "memory",
        "label": "Memory",
        "description": "Conversation and vector memory surface.",
        "contract": "rumiai.slot.memory.v1",
        "multi": False,
        "required_provides": ["defaults.memory.store"],
        "component_types": ["memory"],
        "interface_key": "rumiai.slot.memory",
        "character": "M",
    },
    {
        "slot_id": "provider",
        "label": "Provider",
        "description": "Provider registry and model provider surface.",
        "contract": "rumiai.slot.provider.v1",
        "multi": False,
        "required_provides": ["defaults.ai.providers"],
        "component_types": ["ai_client"],
        "interface_key": "rumiai.slot.provider",
        "character": "P",
    },
]

STANDARD_PACKS: Dict[str, Dict[str, Any]] = {
    "defaultspack": {
        "pack_id": "defaultspack",
        "display_name": "defaultspack",
        "description": "Reference standards pack around the official start node.",
        "character": "D",
    }
}


def can_connect_ports(
    source_direction: str,
    source_contracts: List[str],
    target_direction: str,
    target_contracts: List[str],
) -> bool:
    if source_direction != "output" or target_direction != "input":
        return False
    source_set = {contract for contract in source_contracts if contract}
    target_set = {contract for contract in target_contracts if contract}
    return bool(source_set.intersection(target_set))


def _now_ts() -> int:
    return int(time.time())


class StartupProfileManager:
    def __init__(self, storage_path: Optional[Path] = None) -> None:
        base_dir = Path(__file__).resolve().parent.parent
        self._storage_path = storage_path or (base_dir / "user_data" / "settings" / "startup_profiles.json")

    @property
    def storage_path(self) -> Path:
        return self._storage_path

    def list_profiles_payload(self) -> Dict[str, Any]:
        catalog = self._build_catalog()
        state = self._load_state(catalog)
        return {
            "profiles": copy.deepcopy(state["profiles"]),
            "active_profile_id": state.get("active_profile_id"),
            "last_launched_profile_id": state.get("last_launched_profile_id"),
            "catalog": catalog,
        }

    def create_profile(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        catalog = self._build_catalog()
        state = self._load_state(catalog)
        name = str(payload.get("name") or "").strip() or "New startup profile"
        requested_id = str(payload.get("profile_id") or "").strip()
        profile_id = requested_id or self._unique_profile_id(state["profiles"], name)
        if any(profile["profile_id"] == profile_id for profile in state["profiles"]):
            return {"error": f"Profile '{profile_id}' already exists", "status_code": 409}
        profile = self._profile_from_payload(profile_id, payload, catalog)
        error = self._validate_profile(profile, catalog)
        if error:
            return {"error": error, "status_code": 400}
        profile["name"] = name
        profile["created_at"] = _now_ts()
        profile["updated_at"] = profile["created_at"]
        state["profiles"].append(profile)
        self._save_state(state)
        return {"profile": profile, "created": True}

    def update_profile(self, profile_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        catalog = self._build_catalog()
        state = self._load_state(catalog)
        index = self._find_profile_index(state["profiles"], profile_id)
        if index is None:
            return {"error": f"Profile '{profile_id}' not found", "status_code": 404}
        current = copy.deepcopy(state["profiles"][index])
        merged_payload = {
            "name": payload.get("name", current.get("name")),
            "standard_pack_id": payload.get("standard_pack_id", current.get("standard_pack_id")),
            "slots": payload.get("slots", current.get("slots", {})),
        }
        updated = self._profile_from_payload(profile_id, merged_payload, catalog)
        updated["created_at"] = current.get("created_at", _now_ts())
        updated["updated_at"] = _now_ts()
        error = self._validate_profile(updated, catalog)
        if error:
            return {"error": error, "status_code": 400}
        state["profiles"][index] = updated
        self._save_state(state)
        return {"profile": updated, "updated": True}

    def duplicate_profile(self, profile_id: str) -> Dict[str, Any]:
        catalog = self._build_catalog()
        state = self._load_state(catalog)
        index = self._find_profile_index(state["profiles"], profile_id)
        if index is None:
            return {"error": f"Profile '{profile_id}' not found", "status_code": 404}
        current = copy.deepcopy(state["profiles"][index])
        duplicated = copy.deepcopy(current)
        duplicated["profile_id"] = self._unique_profile_id(state["profiles"], current.get("name", "profile"))
        duplicated["name"] = f"{current.get('name', 'Profile')} Copy"
        duplicated["created_at"] = _now_ts()
        duplicated["updated_at"] = duplicated["created_at"]
        state["profiles"].append(duplicated)
        self._save_state(state)
        return {"profile": duplicated, "duplicated": True}

    def delete_profile(self, profile_id: str) -> Dict[str, Any]:
        catalog = self._build_catalog()
        state = self._load_state(catalog)
        index = self._find_profile_index(state["profiles"], profile_id)
        if index is None:
            return {"error": f"Profile '{profile_id}' not found", "status_code": 404}
        if len(state["profiles"]) <= 1:
            return {"error": "At least one startup profile must remain", "status_code": 400}

        deleted_profile = copy.deepcopy(state["profiles"].pop(index))

        if state.get("active_profile_id") == profile_id:
            state["active_profile_id"] = state["profiles"][0]["profile_id"]
        if state.get("last_launched_profile_id") == profile_id:
            state["last_launched_profile_id"] = None

        self._save_state(state)

        fallback_profile = self._get_profile(state["profiles"], state["active_profile_id"])
        if fallback_profile is not None:
            self._apply_profile_to_active_ecosystem(fallback_profile, catalog, launched=False)

        return {
            "deleted": True,
            "deleted_profile_id": deleted_profile["profile_id"],
            "active_profile_id": state.get("active_profile_id"),
        }

    def activate_profile(self, profile_id: str) -> Dict[str, Any]:
        catalog = self._build_catalog()
        state = self._load_state(catalog)
        profile = self._get_profile(state["profiles"], profile_id)
        if profile is None:
            return {"error": f"Profile '{profile_id}' not found", "status_code": 404}
        error = self._validate_profile(profile, catalog)
        if error:
            return {"error": error, "status_code": 400}
        state["active_profile_id"] = profile_id
        self._save_state(state)
        self._apply_profile_to_active_ecosystem(profile, catalog, launched=False)
        return {"profile": profile, "active_profile_id": profile_id, "activated": True}

    def launch_profile(self, profile_id: str) -> Dict[str, Any]:
        catalog = self._build_catalog()
        state = self._load_state(catalog)
        profile = self._get_profile(state["profiles"], profile_id)
        if profile is None:
            return {"error": f"Profile '{profile_id}' not found", "status_code": 404}
        error = self._validate_profile(profile, catalog)
        if error:
            return {"error": error, "status_code": 400}
        state["active_profile_id"] = profile_id
        state["last_launched_profile_id"] = profile_id
        self._save_state(state)
        self._apply_profile_to_active_ecosystem(profile, catalog, launched=True)
        handoff = self._request_launch_handoff(profile)
        if not handoff.get("restart_requested"):
            return {
                "error": "Runtime handoff is unavailable; startup profile was saved but launch could not complete",
                "status_code": 503,
            }
        return {
            "profile": profile,
            "active_profile_id": profile_id,
            "launched": True,
            "restart_requested": True,
            "handoff": handoff,
        }

    def _load_state(self, catalog: Dict[str, Any]) -> Dict[str, Any]:
        path = self.storage_path
        if path.is_file():
            try:
                state = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                logger.warning("startup_profiles.json is unreadable, regenerating defaults", exc_info=True)
                state = self._default_state(catalog)
        else:
            state = self._default_state(catalog)
        state = self._normalize_state(state, catalog)
        if not path.is_file():
            self._save_state(state)
        return state

    def _save_state(self, state: Dict[str, Any]) -> None:
        path = self.storage_path
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp_path.replace(path)

    def _default_state(self, catalog: Dict[str, Any]) -> Dict[str, Any]:
        default_profile = self._build_default_profile(catalog)
        return {
            "version": 1,
            "active_profile_id": default_profile["profile_id"],
            "last_launched_profile_id": None,
            "profiles": [default_profile],
        }

    def _normalize_state(self, state: Dict[str, Any], catalog: Dict[str, Any]) -> Dict[str, Any]:
        profiles = state.get("profiles")
        if not isinstance(profiles, list) or not profiles:
            normalized = self._default_state(catalog)
            return normalized
        normalized_profiles: List[Dict[str, Any]] = []
        for raw_profile in profiles:
            if not isinstance(raw_profile, dict):
                continue
            profile_id = str(raw_profile.get("profile_id") or "").strip() or f"profile-{uuid.uuid4().hex[:8]}"
            normalized = self._profile_from_payload(profile_id, raw_profile, catalog)
            normalized["name"] = str(raw_profile.get("name") or normalized["name"])
            normalized["created_at"] = int(raw_profile.get("created_at") or _now_ts())
            normalized["updated_at"] = int(raw_profile.get("updated_at") or normalized["created_at"])
            normalized_profiles.append(normalized)
        if not normalized_profiles:
            return self._default_state(catalog)
        active_profile_id = str(state.get("active_profile_id") or normalized_profiles[0]["profile_id"])
        if self._get_profile(normalized_profiles, active_profile_id) is None:
            active_profile_id = normalized_profiles[0]["profile_id"]
        last_launched_profile_id = str(state.get("last_launched_profile_id") or "").strip() or None
        if last_launched_profile_id and self._get_profile(normalized_profiles, last_launched_profile_id) is None:
            last_launched_profile_id = None
        return {
            "version": 1,
            "active_profile_id": active_profile_id,
            "last_launched_profile_id": last_launched_profile_id,
            "profiles": normalized_profiles,
        }

    def _profile_from_payload(
        self,
        profile_id: str,
        payload: Dict[str, Any],
        catalog: Dict[str, Any],
    ) -> Dict[str, Any]:
        standard_pack_id = str(payload.get("standard_pack_id") or self._default_standard_pack_id(catalog))
        slot_payload = payload.get("slots", {})
        slots: Dict[str, str] = {}
        for slot in SLOT_SPECS:
            slot_id = slot["slot_id"]
            slot_value = ""
            if isinstance(slot_payload, dict):
                slot_value = str(slot_payload.get(slot_id) or "").strip()
            if not slot_value:
                slot_value = self._default_slot_binding(slot_id, catalog)
            slots[slot_id] = slot_value
        return {
            "profile_id": profile_id,
            "name": str(payload.get("name") or profile_id),
            "standard_pack_id": standard_pack_id,
            "slots": slots,
        }

    def _default_standard_pack_id(self, catalog: Dict[str, Any]) -> str:
        standard_packs = catalog.get("standard_packs") or []
        for pack in standard_packs:
            if pack.get("available"):
                return str(pack["pack_id"])
        return standard_packs[0]["pack_id"] if standard_packs else "defaultspack"

    def _default_slot_binding(self, slot_id: str, catalog: Dict[str, Any]) -> str:
        for candidate in catalog.get("slot_candidates", {}).get(slot_id, []):
            if candidate.get("pack_id") == "defaultspack":
                return "defaultspack"
        candidates = catalog.get("slot_candidates", {}).get(slot_id, [])
        return str(candidates[0]["pack_id"]) if candidates else ""

    def _build_default_profile(self, catalog: Dict[str, Any]) -> Dict[str, Any]:
        profile = self._profile_from_payload(
            "default-profile",
            {"name": "Default Profile"},
            catalog,
        )
        profile["created_at"] = _now_ts()
        profile["updated_at"] = profile["created_at"]
        return profile

    def _build_catalog(self) -> Dict[str, Any]:
        discovered = self._discover_packs()
        slot_candidates = self._build_slot_candidates(discovered)
        standard_packs = self._build_standard_packs(discovered, slot_candidates)

        return {
            "version": 1,
            "start_node": {
                "node_id": "start",
                "title": "start",
                "subtitle": "Official rumiai entrypoint",
                "kind": "official_start",
                "character": "S",
                "ports": [
                    {
                        "port_id": "standard",
                        "label": "standard pack",
                        "direction": "output",
                        "contracts": [START_CONTRACT],
                        "multi": False,
                    }
                ],
            },
            "slot_specs": [
                {
                    "slot_id": slot["slot_id"],
                    "label": slot["label"],
                    "description": slot["description"],
                    "contract": slot["contract"],
                    "multi": slot["multi"],
                    "interface_key": slot["interface_key"],
                    "character": slot["character"],
                }
                for slot in SLOT_SPECS
            ],
            "standard_packs": standard_packs,
            "slot_candidates": slot_candidates,
        }

    def _discover_packs(self) -> Dict[str, Dict[str, Any]]:
        discovered: Dict[str, Dict[str, Any]] = {}
        enabled_overrides = self._read_pack_enabled_overrides()
        for loc in discover_pack_locations():
            try:
                ecosystem = json.loads(loc.ecosystem_json_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            default_enabled = bool(ecosystem.get("enabled", True))
            enabled = bool(enabled_overrides.get(loc.pack_id, default_enabled))
            discovered[loc.pack_id] = {
                "pack_id": loc.pack_id,
                "pack_identity": str(ecosystem.get("pack_identity", "")),
                "name": str(ecosystem.get("metadata", {}).get("name", loc.pack_id)),
                "description": str(ecosystem.get("metadata", {}).get("description", "")),
                "components": ecosystem.get("components", {}),
                "enabled": enabled,
                "load_order": ecosystem.get("load_order", []),
                "pack_subdir": loc.pack_subdir,
            }
        return discovered

    def _read_pack_enabled_overrides(self) -> Dict[str, bool]:
        path = self.storage_path.parent / "pack_enabled_overrides.json"
        if not path.is_file():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("pack_enabled_overrides.json is unreadable, ignoring overrides", exc_info=True)
            return {}
        if not isinstance(raw, dict):
            return {}
        return {str(key): bool(value) for key, value in raw.items()}

    def _build_standard_packs(
        self,
        discovered: Dict[str, Dict[str, Any]],
        slot_candidates: Dict[str, List[Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        standard_packs: List[Dict[str, Any]] = []
        for pack_id, spec in STANDARD_PACKS.items():
            discovered_pack = discovered.get(pack_id, {})
            runtime_issues = self._standard_pack_runtime_issues(pack_id, discovered, slot_candidates)
            available = bool(discovered_pack) and not runtime_issues
            standard_packs.append(
                {
                    "pack_id": pack_id,
                    "display_name": discovered_pack.get("name", spec["display_name"]),
                    "description": discovered_pack.get("description", spec["description"]),
                    "pack_identity": discovered_pack.get("pack_identity", ""),
                    "available": available,
                    "runtime_ready": not runtime_issues,
                    "runtime_issues": runtime_issues,
                    "enabled": bool(discovered_pack.get("enabled", False)),
                    "character": spec.get("character", "S"),
                    "slots": [
                        {
                            "slot_id": slot["slot_id"],
                            "contract": slot["contract"],
                            "label": slot["label"],
                        }
                        for slot in SLOT_SPECS
                    ],
                }
            )
        return standard_packs

    def _standard_pack_runtime_issues(
        self,
        pack_id: str,
        discovered: Dict[str, Dict[str, Any]],
        slot_candidates: Dict[str, List[Dict[str, Any]]],
    ) -> List[str]:
        pack = discovered.get(pack_id)
        if not pack:
            return [f"Standard pack '{pack_id}' is not installed"]
        issues: List[str] = []
        if not pack.get("enabled", False):
            issues.append(f"Standard pack '{pack_id}' is disabled")
        for slot in SLOT_SPECS:
            candidate = next(
                (
                    item
                    for item in slot_candidates.get(slot["slot_id"], [])
                    if item.get("pack_id") == pack_id and item.get("runtime_ready")
                ),
                None,
            )
            if candidate is None:
                issues.append(f"Standard pack '{pack_id}' has no runtime-ready '{slot['slot_id']}' slot implementation")
        return issues

    def _build_slot_candidates(self, discovered: Dict[str, Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        slot_candidates: Dict[str, List[Dict[str, Any]]] = {slot["slot_id"]: [] for slot in SLOT_SPECS}

        for pack_id, pack in discovered.items():
            for slot in SLOT_SPECS:
                runtime_candidate = self._runtime_candidate_for_slot(slot, pack)
                if runtime_candidate is None:
                    continue

                slot_candidates[slot["slot_id"]].append(
                    {
                        "pack_id": pack_id,
                        "pack_identity": pack.get("pack_identity", ""),
                        "display_name": pack.get("name", pack_id),
                        "description": pack.get("description", ""),
                        "contracts": [slot["contract"]],
                        "component_types": runtime_candidate["component_types"],
                        "provides": runtime_candidate["provides"],
                        "character": (pack.get("name", pack_id) or pack_id)[:1].upper(),
                        "enabled": bool(pack.get("enabled", False)),
                        "runtime_ready": runtime_candidate["runtime_ready"],
                        "runtime_issues": runtime_candidate["runtime_issues"],
                        "selected_component_id": runtime_candidate["selected_component_id"],
                    }
                )

        for slot_id, candidates in slot_candidates.items():
            candidates.sort(
                key=lambda item: (
                    not item.get("runtime_ready", False),
                    item["pack_id"] != "defaultspack",
                    item["display_name"],
                )
            )
        return slot_candidates

    def _runtime_candidate_for_slot(self, slot: Dict[str, Any], pack: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        components = pack.get("components", {})
        if not isinstance(components, dict):
            return None

        matched_component_types: List[str] = []
        matched_provides: List[str] = []
        runtime_issue_map: Dict[str, List[str]] = {}
        ready_component_id: Optional[str] = None

        for component_key, component in components.items():
            if not isinstance(component, dict):
                continue
            component_type = str(component.get("type", "")).strip()
            provides = component.get("connectivity", {}).get("provides", [])
            if not isinstance(provides, list):
                provides = []
            normalized_provides = [str(item) for item in provides if item]
            if component_type not in slot["component_types"]:
                continue
            if not all(required in normalized_provides for required in slot["required_provides"]):
                continue

            matched_component_types.append(component_type)
            matched_provides.extend(normalized_provides)
            component_id = str(component.get("id") or component_key)
            issues = self._component_runtime_issues(component_id, component, pack)
            runtime_issue_map[component_id] = issues
            if not issues and ready_component_id is None:
                ready_component_id = component_id

        if not matched_component_types:
            return None

        runtime_issues: List[str] = []
        if not pack.get("enabled", False):
            runtime_issues.append(f"Pack '{pack['pack_id']}' is disabled")
        if ready_component_id is None:
            for component_id, issues in runtime_issue_map.items():
                if issues:
                    runtime_issues.extend(f"{component_id}: {issue}" for issue in issues)

        return {
            "component_types": sorted(set(matched_component_types)),
            "provides": sorted(set(matched_provides)),
            "runtime_ready": bool(pack.get("enabled", False)) and ready_component_id is not None,
            "runtime_issues": runtime_issues,
            "selected_component_id": ready_component_id or next(iter(runtime_issue_map.keys()), ""),
        }

    def _component_runtime_issues(
        self,
        component_id: str,
        component: Dict[str, Any],
        pack: Dict[str, Any],
    ) -> List[str]:
        issues: List[str] = []
        pack_subdir = pack.get("pack_subdir")
        component_type = str(component.get("type", "")).strip()
        resolved_runtime_id = f"{component_type}:{component_id}" if component_type else component_id

        component_path = str(component.get("path", "")).strip()
        entry = component.get("entry")
        if component_path:
            if isinstance(pack_subdir, (str, Path)):
                component_root = Path(pack_subdir) / component_path
                if not component_root.exists():
                    issues.append(f"path '{component_path}' is missing")
            else:
                issues.append("pack root is missing")
        elif not entry:
            issues.append("component has neither path nor entry")

        load_order = pack.get("load_order", [])
        if isinstance(load_order, list) and load_order and resolved_runtime_id not in {str(item) for item in load_order}:
            issues.append(f"load_order is missing '{resolved_runtime_id}'")

        requires = component.get("connectivity", {}).get("requires", [])
        if isinstance(requires, list) and requires:
            available_types = {
                str(candidate_component.get("type", "")).strip()
                for candidate_component in (pack.get("components", {}) or {}).values()
                if isinstance(candidate_component, dict)
            }
            missing_types = sorted(str(required) for required in requires if str(required) not in available_types)
            if missing_types:
                issues.append(f"missing required component types: {', '.join(missing_types)}")

        return issues

    def _validate_profile(self, profile: Dict[str, Any], catalog: Dict[str, Any]) -> Optional[str]:
        standard_pack_id = profile.get("standard_pack_id")
        standard_pack = next(
            (pack for pack in catalog.get("standard_packs", []) if pack["pack_id"] == standard_pack_id),
            None,
        )
        if standard_pack is None:
            return f"Unknown standard pack '{standard_pack_id}'"
        if not standard_pack.get("available"):
            issues = standard_pack.get("runtime_issues") or []
            suffix = f": {'; '.join(issues)}" if issues else ""
            return f"Standard pack '{standard_pack_id}' is not available{suffix}"

        for slot in SLOT_SPECS:
            slot_id = slot["slot_id"]
            selected_pack = str(profile.get("slots", {}).get(slot_id) or "").strip()
            if not selected_pack:
                return f"Slot '{slot_id}' requires a pack selection"
            candidate = next(
                (
                    item
                    for item in catalog.get("slot_candidates", {}).get(slot_id, [])
                    if item.get("pack_id") == selected_pack
                ),
                None,
            )
            if candidate is None:
                return f"Pack '{selected_pack}' does not satisfy slot '{slot_id}'"
            if not can_connect_ports(
                "output",
                [slot["contract"]],
                "input",
                candidate.get("contracts", []),
            ):
                return f"Contract mismatch between slot '{slot_id}' and pack '{selected_pack}'"
            if not candidate.get("runtime_ready", False):
                issues = candidate.get("runtime_issues") or []
                suffix = f": {'; '.join(issues)}" if issues else ""
                return f"Pack '{selected_pack}' is not runtime-ready for slot '{slot_id}'{suffix}"
        return None

    def _apply_profile_to_active_ecosystem(
        self,
        profile: Dict[str, Any],
        catalog: Dict[str, Any],
        *,
        launched: bool,
    ) -> None:
        try:
            from backend_core.ecosystem.active_ecosystem import get_active_ecosystem_manager
        except Exception:
            logger.debug("active ecosystem manager is unavailable", exc_info=True)
            return

        try:
            active = get_active_ecosystem_manager()
        except Exception:
            logger.debug("failed to load active ecosystem manager", exc_info=True)
            return

        standard_pack = next(
            (pack for pack in catalog.get("standard_packs", []) if pack["pack_id"] == profile["standard_pack_id"]),
            None,
        )
        if standard_pack and standard_pack.get("pack_identity"):
            active.active_pack_identity = standard_pack["pack_identity"]

        active.set_metadata("startup_profile_id", profile["profile_id"])
        active.set_metadata("startup_standard_pack_id", profile["standard_pack_id"])
        active.set_metadata("startup_slots", dict(profile.get("slots", {})))
        active.set_metadata("startup_launched", bool(launched))
        active.set_metadata("startup_launch_requested_at", _now_ts() if launched else None)

        for slot in SLOT_SPECS:
            interface_key = slot["interface_key"]
            pack_id = str(profile.get("slots", {}).get(slot["slot_id"]) or "").strip()
            if pack_id:
                active.set_interface_override(interface_key, pack_id)
                for extra_key in slot.get("extra_interface_keys", []):
                    active.set_interface_override(extra_key, pack_id)
            else:
                active.remove_interface_override(interface_key)
                for extra_key in slot.get("extra_interface_keys", []):
                    active.remove_interface_override(extra_key)

    def _request_launch_handoff(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from .api.control_panel_handlers import _RESTART_EXIT_CODE, request_kernel_restart
        except Exception:
            logger.debug("kernel restart request helper is unavailable", exc_info=True)
            return {
                "kind": "active_ecosystem_only",
                "reason": "startup_profile_launch",
                "restart_requested": False,
            }

        request_kernel_restart()
        return {
            "kind": "kernel_restart",
            "reason": "startup_profile_launch",
            "restart_requested": True,
            "exit_code": _RESTART_EXIT_CODE,
            "profile_id": profile["profile_id"],
        }

    @staticmethod
    def _find_profile_index(profiles: List[Dict[str, Any]], profile_id: str) -> Optional[int]:
        for index, profile in enumerate(profiles):
            if profile.get("profile_id") == profile_id:
                return index
        return None

    @staticmethod
    def _get_profile(profiles: List[Dict[str, Any]], profile_id: str) -> Optional[Dict[str, Any]]:
        for profile in profiles:
            if profile.get("profile_id") == profile_id:
                return profile
        return None

    @staticmethod
    def _unique_profile_id(profiles: List[Dict[str, Any]], seed: str) -> str:
        base = "-".join(
            chunk
            for chunk in "".join(char.lower() if char.isalnum() else "-" for char in seed).split("-")
            if chunk
        ) or "startup-profile"
        candidate = base
        suffix = 2
        existing = {profile.get("profile_id") for profile in profiles}
        while candidate in existing:
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate
