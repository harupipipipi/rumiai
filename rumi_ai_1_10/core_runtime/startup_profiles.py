from __future__ import annotations

import copy
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .paths import discover_pack_locations
from .node_models import make_core_start_node
from .port_standards import can_connect_ports as _can_connect_standard_ports

logger = logging.getLogger(__name__)

PROFILE_VERSION = 3
START_CONTRACT = "rumiai.start.standard.v1"

# --- graph loader (lazy import to avoid circular dependency) ---
_graph_loader = None


def _get_graph_loader():
    global _graph_loader
    if _graph_loader is None:
        try:
            from .graph_loader import load_graph_file
            _graph_loader = load_graph_file
        except ImportError:
            _graph_loader = _load_graph_from_yaml
    return _graph_loader


def _load_graph_from_yaml(path: Path) -> Optional[Any]:
    """Fallback graph loader using yaml."""
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        from .graph_models import load_graph_document
        return load_graph_document(data, source_path=str(path))
    except Exception:
        logger.debug("Failed to load graph from %s", path, exc_info=True)
        return None


def can_connect_ports(
    source_direction: str,
    source_contracts: List[str],
    target_direction: str,
    target_contracts: List[str],
) -> bool:
    return _can_connect_standard_ports(
        source_direction,
        source_contracts,
        target_direction,
        target_contracts,
    )


def _now_ts() -> int:
    return int(time.time())


class StartupProfileManager:
    def __init__(
        self,
        storage_path: Optional[Path] = None,
        *,
        interface_registry: Any = None,
        approval_manager: Any = None,
        ecosystem_dir: Optional[str] = None,
        seed_default_profile: Optional[bool] = None,
    ) -> None:
        base_dir = Path(__file__).resolve().parent.parent
        user_data_dir = Path(os.environ.get("RUMI_USER_DATA") or (base_dir / "user_data"))
        self._storage_path = storage_path or (user_data_dir / "settings" / "startup_profiles.json")
        self.interface_registry = interface_registry
        self.approval_manager = approval_manager
        self.ecosystem_dir = ecosystem_dir
        self.seed_default_profile = storage_path is None if seed_default_profile is None else seed_default_profile

    @property
    def storage_path(self) -> Path:
        return self._storage_path

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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

        base_pack = str(payload.get("base_pack") or "").strip()
        if not base_pack:
            return {"error": "base_pack is required", "status_code": 400}

        available_pack_ids = {pack["pack_id"] for pack in catalog.get("packs", []) if pack.get("available")}
        if base_pack not in available_pack_ids:
            return {"error": f"Base pack '{base_pack}' is not available", "status_code": 400}

        graph_id = str(payload.get("graph_id") or "").strip()
        if not graph_id:
            graph_id = self._default_graph_for_pack(base_pack, catalog)
        if not graph_id:
            return {"error": f"No graph found for base pack '{base_pack}'", "status_code": 400}

        graph_ports = self._extract_graph_ports(graph_id, base_pack, catalog)
        if not graph_ports:
            return {"error": f"Graph '{graph_id}' has no overridable ports", "status_code": 400}

        name = str(payload.get("name") or "").strip() or "New startup profile"
        requested_id = str(payload.get("profile_id") or "").strip()
        profile_id = requested_id or self._unique_profile_id(state["profiles"], name)
        if any(profile["profile_id"] == profile_id for profile in state["profiles"]):
            return {"error": f"Profile '{profile_id}' already exists", "status_code": 409}

        profile = {
            "version": PROFILE_VERSION,
            "profile_id": profile_id,
            "name": name,
            "base_pack": base_pack,
            "graph_id": graph_id,
            "graph_ports": graph_ports,
            "packs": [base_pack],
            "node_overrides": {},
            **self._runtime_profile_fields(profile_id, payload),
        }
        profile["created_at"] = _now_ts()
        profile["updated_at"] = profile["created_at"]

        error = self._validate_profile(profile, catalog)
        if error:
            return {"error": error, "status_code": 400}

        state["profiles"].append(profile)
        if state.get("active_profile_id") is None:
            state["active_profile_id"] = profile_id
        self._save_state(state)
        return {"profile": profile, "created": True}

    def update_profile(self, profile_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        catalog = self._build_catalog()
        state = self._load_state(catalog)
        index = self._find_profile_index(state["profiles"], profile_id)
        if index is None:
            return {"error": f"Profile '{profile_id}' not found", "status_code": 404}
        current = copy.deepcopy(state["profiles"][index])

        new_name = payload.get("name", current.get("name"))
        new_base_pack = payload.get("base_pack", current.get("base_pack"))
        new_graph_id = payload.get("graph_id", current.get("graph_id"))
        new_packs = payload.get("packs", current.get("packs", []))
        new_node_overrides = payload.get("node_overrides", current.get("node_overrides", {}))

        graph_ports = current.get("graph_ports", [])
        if new_base_pack and new_graph_id:
            graph_ports = self._extract_graph_ports(new_graph_id, new_base_pack, catalog)

        merged_payload = {
            "name": new_name,
            "base_pack": new_base_pack,
            "graph_id": new_graph_id,
            "packs": new_packs,
            "node_overrides": new_node_overrides,
        }
        for field_name in self._runtime_profile_field_names():
            if field_name in payload or field_name in current:
                merged_payload[field_name] = payload.get(field_name, current.get(field_name))

        updated = {
            "version": PROFILE_VERSION,
            "profile_id": profile_id,
            "name": str(merged_payload.get("name") or profile_id),
            "base_pack": str(merged_payload.get("base_pack") or ""),
            "graph_id": str(merged_payload.get("graph_id") or ""),
            "graph_ports": graph_ports,
            "packs": list(merged_payload.get("packs") or []),
            "node_overrides": dict(merged_payload.get("node_overrides") or {}),
            **self._runtime_profile_fields(profile_id, merged_payload),
        }
        updated["created_at"] = current.get("created_at", _now_ts())
        updated["updated_at"] = _now_ts()

        error = self._validate_profile(updated, catalog)
        if error:
            return {"error": error, "status_code": 400}
        state["profiles"][index] = updated
        self._save_state(state)
        return {"profile": updated, "updated": True}

    def add_pack_to_profile(self, profile_id: str, pack_id: str) -> Dict[str, Any]:
        catalog = self._build_catalog()
        state = self._load_state(catalog)
        index = self._find_profile_index(state["profiles"], profile_id)
        if index is None:
            return {"error": f"Profile '{profile_id}' not found", "status_code": 404}
        available_pack_ids = {pack["pack_id"] for pack in catalog.get("packs", []) if pack.get("available")}
        if pack_id not in available_pack_ids:
            return {"error": f"Pack '{pack_id}' is not available", "status_code": 400}
        profile = copy.deepcopy(state["profiles"][index])
        packs = list(profile.get("packs") or [])
        if pack_id in packs:
            return {"error": f"Pack '{pack_id}' is already in profile", "status_code": 409}
        packs.append(pack_id)
        profile["packs"] = packs
        profile["updated_at"] = _now_ts()
        state["profiles"][index] = profile
        self._save_state(state)
        return {"profile": profile, "pack_added": pack_id}

    def remove_pack_from_profile(self, profile_id: str, pack_id: str) -> Dict[str, Any]:
        catalog = self._build_catalog()
        state = self._load_state(catalog)
        index = self._find_profile_index(state["profiles"], profile_id)
        if index is None:
            return {"error": f"Profile '{profile_id}' not found", "status_code": 404}
        profile = copy.deepcopy(state["profiles"][index])
        base_pack = profile.get("base_pack", "")
        if pack_id == base_pack:
            return {"error": "Cannot remove the base pack from the profile", "status_code": 400}
        packs = list(profile.get("packs") or [])
        if pack_id not in packs:
            return {"error": f"Pack '{pack_id}' is not in profile", "status_code": 404}
        packs.remove(pack_id)
        profile["packs"] = packs
        overrides = dict(profile.get("node_overrides") or {})
        for port_key, target_node in list(overrides.items()):
            target_pack = target_node.split(".")[0] if "." in target_node else ""
            if target_pack == pack_id:
                del overrides[port_key]
        profile["node_overrides"] = overrides
        profile["updated_at"] = _now_ts()
        state["profiles"][index] = profile
        self._save_state(state)
        return {"profile": profile, "pack_removed": pack_id}

    def set_node_override(self, profile_id: str, port_key: str, node_id: str) -> Dict[str, Any]:
        catalog = self._build_catalog()
        state = self._load_state(catalog)
        index = self._find_profile_index(state["profiles"], profile_id)
        if index is None:
            return {"error": f"Profile '{profile_id}' not found", "status_code": 404}
        profile = copy.deepcopy(state["profiles"][index])
        graph_ports = profile.get("graph_ports", [])
        node_catalog = self._list_available_nodes(profile.get("packs", []), catalog)
        error = self._validate_node_override(port_key, node_id, graph_ports, node_catalog)
        if error:
            return {"error": error, "status_code": 400}
        overrides = dict(profile.get("node_overrides") or {})
        overrides[port_key] = node_id
        profile["node_overrides"] = overrides
        profile["updated_at"] = _now_ts()
        error = self._validate_profile(profile, catalog)
        if error:
            return {"error": error, "status_code": 400}
        state["profiles"][index] = profile
        self._save_state(state)
        return {"profile": profile, "override_set": {"port_key": port_key, "node_id": node_id}}

    def clear_node_override(self, profile_id: str, port_key: str) -> Dict[str, Any]:
        catalog = self._build_catalog()
        state = self._load_state(catalog)
        index = self._find_profile_index(state["profiles"], profile_id)
        if index is None:
            return {"error": f"Profile '{profile_id}' not found", "status_code": 404}
        profile = copy.deepcopy(state["profiles"][index])
        overrides = dict(profile.get("node_overrides") or {})
        if port_key not in overrides:
            return {"error": f"No override set for port '{port_key}'", "status_code": 404}
        del overrides[port_key]
        profile["node_overrides"] = overrides
        profile["updated_at"] = _now_ts()
        state["profiles"][index] = profile
        self._save_state(state)
        return {"profile": profile, "override_cleared": port_key}

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
        capability_graph = self._compile_launch_capability_graph(profile)
        raw_policy = profile.get("policy")
        policy = raw_policy if isinstance(raw_policy, dict) else {}
        if policy.get("require_capability_graph_compile") is True and not capability_graph.get("ok"):
            return {
                "error": "Capability graph compile failed for strict startup profile",
                "status_code": 400,
                "profile": profile,
                "active_profile_id": state.get("active_profile_id"),
                "launched": False,
                "capability_graph": capability_graph,
            }
        if capability_graph.get("runtime_profile_key"):
            profile["last_runtime_profile_key"] = capability_graph["runtime_profile_key"]
            index = self._find_profile_index(state["profiles"], profile_id)
            if index is not None:
                state["profiles"][index] = profile
        state["active_profile_id"] = profile_id
        state["last_launched_profile_id"] = profile_id
        self._save_state(state)
        self._apply_profile_to_active_ecosystem(profile, catalog, launched=True)
        self._record_capability_graph_result(capability_graph)
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
            "capability_graph": capability_graph,
        }

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def _load_state(self, catalog: Dict[str, Any]) -> Dict[str, Any]:
        path = self.storage_path
        if path.is_file():
            try:
                state = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                logger.warning("startup_profiles.json is unreadable, resetting", exc_info=True)
                state = self._default_state(catalog)
        else:
            state = self._default_state(catalog)
        normalized_state = self._normalize_state(state, catalog)
        if not path.is_file() or normalized_state != state:
            self._save_state(normalized_state)
        return normalized_state

    def _save_state(self, state: Dict[str, Any]) -> None:
        path = self.storage_path
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp_path.replace(path)

    def _default_state(self, catalog: Dict[str, Any]) -> Dict[str, Any]:
        default_profile = self._default_startup_profile(catalog) if self.seed_default_profile else None
        if default_profile:
            return {
                "version": PROFILE_VERSION,
                "active_profile_id": default_profile["profile_id"],
                "last_launched_profile_id": None,
                "profiles": [default_profile],
            }
        return {
            "version": PROFILE_VERSION,
            "active_profile_id": None,
            "last_launched_profile_id": None,
            "profiles": [],
        }

    def _default_startup_profile(self, catalog: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        preferred_pack_ids = ("defaultspack", "defaults")
        packs = list(catalog.get("packs", []))
        ordered_packs = [
            pack
            for preferred in preferred_pack_ids
            for pack in packs
            if pack.get("pack_id") == preferred
        ]
        ordered_packs.extend(
            pack
            for pack in packs
            if pack.get("pack_id") not in preferred_pack_ids
        )

        for pack_info in ordered_packs:
            base_pack = str(pack_info.get("pack_id") or "").strip()
            if not base_pack:
                continue
            graph_id = self._default_graph_for_pack(base_pack, catalog)
            graph_ports = self._extract_graph_ports(graph_id, base_pack, catalog) if graph_id else []
            if not graph_id or not graph_ports:
                continue
            created_at = _now_ts()
            return {
                "version": PROFILE_VERSION,
                "profile_id": "default-profile",
                "name": "Default Profile",
                "base_pack": base_pack,
                "graph_id": graph_id,
                "graph_ports": graph_ports,
                "packs": [base_pack],
                "node_overrides": {},
                "created_at": created_at,
                "updated_at": created_at,
                **self._runtime_profile_fields(
                    "default-profile",
                    {
                        "name": "Default Profile",
                        "display_name": {"en": "Default Profile", "ja": "Default Profile"},
                    },
                ),
            }
        return None

    def _normalize_state(self, state: Dict[str, Any], catalog: Dict[str, Any]) -> Dict[str, Any]:
        profiles = state.get("profiles")
        if not isinstance(profiles, list):
            return self._default_state(catalog)

        normalized_profiles: List[Dict[str, Any]] = []
        for raw_profile in profiles:
            if not isinstance(raw_profile, dict):
                continue
            profile_id = str(raw_profile.get("profile_id") or "").strip() or f"profile-{uuid.uuid4().hex[:8]}"
            version = raw_profile.get("version")
            if version == PROFILE_VERSION and raw_profile.get("base_pack"):
                normalized = copy.deepcopy(raw_profile)
                normalized["profile_id"] = profile_id
            else:
                normalized = self._migrate_profile(profile_id, raw_profile, catalog)
            normalized["name"] = str(raw_profile.get("name") or normalized.get("name") or profile_id)
            normalized["created_at"] = int(raw_profile.get("created_at") or _now_ts())
            normalized["updated_at"] = int(raw_profile.get("updated_at") or normalized["created_at"])
            normalized_profiles.append(normalized)

        if not normalized_profiles:
            return self._default_state(catalog)

        active_profile_id = str(state.get("active_profile_id") or "").strip() or None
        if active_profile_id and self._get_profile(normalized_profiles, active_profile_id) is None:
            active_profile_id = None
        if active_profile_id is None:
            active_profile_id = normalized_profiles[0]["profile_id"]

        last_launched_profile_id = str(state.get("last_launched_profile_id") or "").strip() or None
        if last_launched_profile_id and self._get_profile(normalized_profiles, last_launched_profile_id) is None:
            last_launched_profile_id = None

        return {
            "version": PROFILE_VERSION,
            "active_profile_id": active_profile_id,
            "last_launched_profile_id": last_launched_profile_id,
            "profiles": normalized_profiles,
        }

    def _migrate_profile(
        self,
        profile_id: str,
        raw: Dict[str, Any],
        catalog: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Migrate a v1/v2 (slot-based) profile to v3 (graph-based)."""
        base_pack = str(raw.get("standard_pack_id") or raw.get("base_pack") or "").strip()
        if not base_pack:
            pack_ids = [pack["pack_id"] for pack in catalog.get("packs", []) if pack.get("available")]
            base_pack = pack_ids[0] if pack_ids else "defaultspack"

        graph_id = self._default_graph_for_pack(base_pack, catalog)
        graph_ports = self._extract_graph_ports(graph_id, base_pack, catalog) if graph_id else []

        node_overrides: Dict[str, str] = {}
        old_slots = raw.get("slots")
        if isinstance(old_slots, dict) and graph_ports:
            _slot_to_port = {
                "tool": "agent.tools",
                "ai_client": "agent.ai",
                "memory": "agent.memory",
                "provider": "agent.ai",
            }
            for slot_id, pack_id in old_slots.items():
                port_key = _slot_to_port.get(slot_id)
                if port_key and pack_id and pack_id != base_pack:
                    override_node = self._find_node_for_pack(pack_id, slot_id, catalog)
                    if override_node:
                        node_overrides[port_key] = override_node

        packs = [base_pack]
        if isinstance(old_slots, dict):
            for pack_id in old_slots.values():
                if pack_id and pack_id not in packs:
                    packs.append(pack_id)
        if not packs:
            packs = [base_pack]

        runtime = self._runtime_profile_fields(profile_id, raw)
        return {
            "version": PROFILE_VERSION,
            "profile_id": profile_id,
            "name": str(raw.get("name") or profile_id),
            "base_pack": base_pack,
            "graph_id": graph_id or "",
            "graph_ports": graph_ports,
            "packs": packs,
            "node_overrides": node_overrides,
            **runtime,
        }

    def _default_graph_for_pack(self, pack_id: str, catalog: Dict[str, Any]) -> str:
        for pack_info in catalog.get("packs", []):
            if pack_info.get("pack_id") == pack_id:
                graphs = pack_info.get("graphs", [])
                for g in graphs:
                    gid = g.get("graph_id", "")
                    if "startup" in gid.lower():
                        return gid
                if graphs:
                    return graphs[0].get("graph_id", "")
        return f"{pack_id}.startup"

    def _find_node_for_pack(self, pack_id: str, slot_id: str, catalog: Dict[str, Any]) -> str:
        for pack_info in catalog.get("packs", []):
            if pack_info.get("pack_id") == pack_id:
                for node in pack_info.get("nodes", []):
                    ref = node.get("ref", "")
                    node_pack = ref.split(".")[0] if "." in ref else ""
                    node_name = ref.split(".")[-1] if "." in ref else ref
                    if node_pack == pack_id:
                        if slot_id == "tool" and "tool" in node_name:
                            return ref
                        if slot_id == "ai_client" and "ai" in node_name:
                            return ref
                        if slot_id == "memory" and "memory" in node_name:
                            return ref
                        if slot_id == "frontend" and "frontend" in node_name:
                            return ref
                for node in pack_info.get("nodes", []):
                    return node.get("ref", "")
        return ""

    # ------------------------------------------------------------------
    # Catalog
    # ------------------------------------------------------------------

    def _build_catalog(self) -> Dict[str, Any]:
        discovered = self._discover_packs()
        packs: List[Dict[str, Any]] = []
        for pack_id, pack_info in discovered.items():
            available = pack_info.get("enabled", False) and not pack_info.get("approval_issues")
            graphs = self._discover_graphs_for_pack(pack_id, pack_info.get("pack_subdir"))
            nodes = self._discover_nodes_for_pack(pack_id, pack_info.get("pack_subdir"))
            packs.append({
                "pack_id": pack_id,
                "name": pack_info.get("name", pack_id),
                "description": pack_info.get("description", ""),
                "pack_identity": pack_info.get("pack_identity", ""),
                "available": available,
                "enabled": pack_info.get("enabled", False),
                "approval_issues": pack_info.get("approval_issues", []),
                "graphs": graphs,
                "nodes": nodes,
            })

        return {
            "version": 2,
            "packs": packs,
        }

    def _discover_graphs_for_pack(self, pack_id: str, pack_subdir: Any) -> List[Dict[str, Any]]:
        if not pack_subdir:
            return []
        graphs_dir = Path(pack_subdir) / "graphs"
        if not graphs_dir.is_dir():
            return []
        result: List[Dict[str, Any]] = []
        loader = _get_graph_loader()
        for f in sorted(graphs_dir.iterdir()):
            if not f.is_file():
                continue
            if f.suffix not in (".yaml", ".yml", ".json"):
                continue
            try:
                graph = loader(f)
                if graph is not None:
                    result.append({
                        "graph_id": graph.graph_id,
                        "display_name": dict(graph.display_name),
                        "description": dict(graph.description),
                        "node_count": len(graph.nodes),
                        "edge_count": len(graph.edges),
                    })
            except Exception:
                logger.debug("Failed to load graph %s", f, exc_info=True)
        return result

    def _discover_nodes_for_pack(self, pack_id: str, pack_subdir: Any) -> List[Dict[str, Any]]:
        if not pack_subdir:
            return []
        nodes_dir = Path(pack_subdir) / "nodes"
        result: List[Dict[str, Any]] = self._core_builtin_nodes_for_pack(pack_id)
        if not nodes_dir.is_dir():
            return result
        for f in sorted(nodes_dir.glob("*.node.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                from .node_models import load_node_document
                definitions = load_node_document(data, source_path=str(f), pack_id=pack_id)
                for node in definitions:
                    metadata = dict(node.metadata)
                    component_id = str(metadata.get("component_id") or node.node_id.rsplit(".", 1)[-1])
                    component_type = str(metadata.get("component_type") or component_id)
                    result.append({
                        "node_id": node.node_id,
                        "kind": node.kind,
                        "component_id": component_id,
                        "component_type": component_type,
                        "metadata": metadata,
                        "display_name": dict(node.display_name),
                        "ports": [port.to_dict() for port in node.ports] if hasattr(node, "ports") else [],
                    })
            except Exception:
                logger.debug("Failed to load node %s", f, exc_info=True)
        return result

    def _core_builtin_nodes_for_pack(self, pack_id: str) -> List[Dict[str, Any]]:
        start_node = make_core_start_node()
        node = start_node.to_dict()
        metadata = dict(node.get("metadata") or {})
        metadata.setdefault("pack_id", pack_id)
        metadata["available_in_pack"] = pack_id
        node["metadata"] = metadata
        return [
            {
                "node_id": start_node.node_id,
                "kind": start_node.kind,
                "component_id": start_node.node_id.rsplit(".", 1)[-1],
                "component_type": "flow_start",
                "metadata": metadata,
                "display_name": dict(start_node.display_name),
                "ports": [port.to_dict() for port in start_node.ports],
            }
        ]

    # ------------------------------------------------------------------
    # Port extraction from graphs
    # ------------------------------------------------------------------

    def _extract_graph_ports(
        self,
        graph_id: str,
        pack_id: str,
        catalog: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Extract overridable input ports from a graph's edges.

        Each edge's 'target' (format: '{node_id}.{port_id}') represents
        an input that could be overridden.  The corresponding 'source'
        shows which node currently provides it.
        """
        graph = self._load_graph_definition(graph_id, pack_id, catalog)
        if graph is None:
            return []

        node_ref_by_id = {node.id: node.ref for node in graph.nodes}
        catalog_nodes = {
            node.get("node_id"): node
            for pack_info in catalog.get("packs", [])
            for node in pack_info.get("nodes", [])
            if node.get("node_id")
        }
        port_map: Dict[str, Dict[str, Any]] = {}

        for edge in graph.edges:
            target_key = edge.target.to_string()
            source_key = edge.source.to_string()
            source_node_id = edge.source.node_id
            source_node_ref = node_ref_by_id.get(source_node_id, "")
            target_node_ref = node_ref_by_id.get(edge.target.node_id, "")
            source_node = catalog_nodes.get(source_node_ref, {})
            target_node = catalog_nodes.get(target_node_ref, {})
            source_port = self._find_port(source_node.get("ports", []), edge.source.port_id)
            target_port = self._find_port(target_node.get("ports", []), edge.target.port_id)

            if target_key not in port_map:
                port_map[target_key] = {
                    "port_key": target_key,
                    "node_id": edge.target.node_id,
                    "port_id": edge.target.port_id,
                    "target_node_ref": target_node_ref,
                    "target_port": target_port,
                    "source_node_id": source_node_id,
                    "source_node_ref": source_node_ref,
                    "source_port_id": edge.source.port_id,
                    "source_port": source_port,
                    "source_ref": source_key,
                }

        return sorted(port_map.values(), key=lambda p: p["port_key"])

    def _load_graph_definition(self, graph_id: str, pack_id: str, catalog: Dict[str, Any]) -> Any:
        for pack_info in catalog.get("packs", []):
            if pack_info.get("pack_id") != pack_id:
                continue
            pack_subdir = None
            for loc in discover_pack_locations(self.ecosystem_dir):
                if loc.pack_id == pack_id:
                    pack_subdir = loc.pack_subdir
                    break
            if not pack_subdir:
                return None
            graphs_dir = Path(pack_subdir) / "graphs"
            if not graphs_dir.is_dir():
                return None
            loader = _get_graph_loader()
            for f in sorted(graphs_dir.iterdir()):
                if not f.is_file() or f.suffix not in (".yaml", ".yml", ".json"):
                    continue
                try:
                    graph = loader(f)
                    if graph is not None and graph.graph_id == graph_id:
                        return graph
                except Exception:
                    continue
        return None

    # ------------------------------------------------------------------
    # Node catalog
    # ------------------------------------------------------------------

    def _list_available_nodes(
        self,
        pack_ids: List[str],
        catalog: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """List all nodes from the specified packs."""
        result: List[Dict[str, Any]] = []
        for pack_info in catalog.get("packs", []):
            if pack_info.get("pack_id") not in pack_ids:
                continue
            for node in pack_info.get("nodes", []):
                node_id = node.get("node_id", "")
                # node_id is already fully qualified (e.g. "coolpack.ai_client")
                result.append({
                    "node_id": node_id,
                    "ref": node_id,
                    "pack_id": pack_info["pack_id"],
                    "component_id": node.get("component_id") or node_id.rsplit(".", 1)[-1],
                    "component_type": node.get("component_type") or node.get("component_id") or node_id.rsplit(".", 1)[-1],
                    "kind": node.get("kind", ""),
                    "metadata": node.get("metadata", {}),
                    "ports": node.get("ports", []),
                    "display_name": node.get("display_name", {}),
                    "pack_available": pack_info.get("available", False),
                })
        result.sort(key=lambda n: (n["pack_id"], n["node_id"]))
        return result

    def _find_port(self, ports: List[Dict[str, Any]], port_id: str) -> Dict[str, Any]:
        for port in ports:
            current_id = str(port.get("id") or port.get("port_id") or "")
            if current_id == port_id:
                return dict(port)
        return {}

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_node_override(
        self,
        port_key: str,
        target_node: str,
        graph_ports: List[Dict[str, Any]],
        node_catalog: List[Dict[str, Any]],
    ) -> Optional[str]:
        valid_port_keys = {p["port_key"] for p in graph_ports}
        if port_key not in valid_port_keys:
            return f"Port '{port_key}' is not a valid graph port. Valid: {sorted(valid_port_keys)}"

        available_nodes = {n["ref"]: n for n in node_catalog if n.get("pack_available")}
        available_refs = set(available_nodes)
        if target_node not in available_refs:
            return f"Node '{target_node}' is not available. Available: {sorted(available_refs)}"

        graph_port = next((p for p in graph_ports if p.get("port_key") == port_key), {})
        target_port = graph_port.get("target_port") or {}
        if not target_port:
            return f"Port '{port_key}' cannot be overridden because its graph target port is unknown"

        target_node_info = available_nodes.get(target_node, {})
        output_ports = [
            port
            for port in target_node_info.get("metadata", {}).get("ports", [])
            if str(port.get("direction") or "") == "output"
        ]
        if not output_ports:
            output_ports = [
                port
                for port in target_node_info.get("ports", [])
                if str(port.get("direction") or "") == "output"
            ]
        compatible = any(
            can_connect_ports(
                str(output_port.get("direction") or ""),
                list(output_port.get("standards") or output_port.get("contracts") or []),
                str(target_port.get("direction") or ""),
                list(target_port.get("standards") or target_port.get("contracts") or []),
            )
            for output_port in output_ports
        )
        if not compatible:
            required = target_port.get("standards") or target_port.get("contracts") or []
            provided = sorted({
                standard
                for output_port in output_ports
                for standard in (output_port.get("standards") or output_port.get("contracts") or [])
            })
            return (
                f"Node '{target_node}' does not satisfy port '{port_key}'. "
                f"Required standards: {list(required)}. Provided standards: {provided}"
            )

        return None

    def _validate_profile(self, profile: Dict[str, Any], catalog: Dict[str, Any]) -> Optional[str]:
        base_pack = profile.get("base_pack")
        if not base_pack:
            return "base_pack is required"

        catalog_pack = next(
            (p for p in catalog.get("packs", []) if p["pack_id"] == base_pack),
            None,
        )
        if catalog_pack is None:
            return f"Unknown base pack '{base_pack}'"
        if not catalog_pack.get("available"):
            issues = catalog_pack.get("approval_issues") or []
            suffix = f": {'; '.join(issues)}" if issues else ""
            return f"Base pack '{base_pack}' is not available{suffix}"

        graph_id = profile.get("graph_id")
        if not graph_id:
            return "graph_id is required"
        graph_ids = {g.get("graph_id") for g in catalog_pack.get("graphs", [])}
        if graph_id not in graph_ids:
            return f"Graph '{graph_id}' not found in pack '{base_pack}'"

        packs = profile.get("packs") or []
        if base_pack not in packs:
            return f"Base pack '{base_pack}' must be included in profile packs"
        available_pack_ids = {p["pack_id"] for p in catalog.get("packs", []) if p.get("available")}
        for pack_id in packs:
            if pack_id not in available_pack_ids:
                return f"Pack '{pack_id}' in profile is not available"

        graph_ports = profile.get("graph_ports") or []
        node_overrides = profile.get("node_overrides") or {}
        node_catalog = self._list_available_nodes(packs, catalog)
        for port_key, target_node in node_overrides.items():
            error = self._validate_node_override(port_key, target_node, graph_ports, node_catalog)
            if error:
                return error

        runtime_bindings = self._resolve_runtime_component_bindings(profile, catalog)
        conflicts = runtime_bindings.get("conflicts") or []
        if conflicts:
            first = conflicts[0]
            return (
                f"Component binding conflict for '{first.get('component_type')}': "
                f"{first.get('existing_component_full_id')} conflicts with "
                f"{first.get('new_component_full_id')} at {first.get('port_key')}"
            )

        return None

    # ------------------------------------------------------------------
    # Capability graph compilation
    # ------------------------------------------------------------------

    def _compile_launch_capability_graph(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        if not profile.get("launch_capability_graph"):
            return {
                "ok": True,
                "skipped": True,
                "reason": "launch_capability_graph_disabled",
                "graph_id": profile.get("graph_id"),
                "capability_profile_id": profile.get("capability_profile_id"),
                "runtime_profile_key": None,
                "runtime_profile": None,
                "diagnostics": [
                    {
                        "level": "info",
                        "code": "startup_capability_graph_not_enabled",
                        "message": "Startup capability graph compile is not enabled for this profile",
                    }
                ],
            }

        if self.interface_registry is None:
            return {
                "ok": False,
                "skipped": False,
                "reason": None,
                "graph_id": profile.get("graph_id"),
                "capability_profile_id": profile.get("capability_profile_id"),
                "runtime_profile_key": None,
                "runtime_profile": None,
                "diagnostics": [
                    {
                        "level": "warning",
                        "code": "interface_registry_unavailable",
                        "message": "Startup capability graph compile requires an InterfaceRegistry",
                    }
                ],
            }

        from .startup_capability_bridge import compile_startup_capabilities

        return compile_startup_capabilities(
            profile,
            interface_registry=self.interface_registry,
            approval_manager=self.approval_manager,
            ecosystem_dir=self.ecosystem_dir,
        ).to_dict()

    def _record_capability_graph_result(self, capability_graph: Dict[str, Any]) -> None:
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

        active.set_metadata(
            "startup_capability_graph",
            {
                "ok": bool(capability_graph.get("ok")),
                "skipped": bool(capability_graph.get("skipped", False)),
                "reason": capability_graph.get("reason"),
                "graph_id": capability_graph.get("graph_id"),
                "capability_profile_id": capability_graph.get("capability_profile_id"),
                "runtime_profile_key": capability_graph.get("runtime_profile_key"),
                "diagnostics": list(capability_graph.get("diagnostics") or []),
            },
        )

    # ------------------------------------------------------------------
    # Apply profile to active ecosystem
    # ------------------------------------------------------------------

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

        catalog_pack = next(
            (p for p in catalog.get("packs", []) if p["pack_id"] == profile.get("base_pack")),
            None,
        )
        if catalog_pack and catalog_pack.get("pack_identity"):
            active.active_pack_identity = catalog_pack["pack_identity"]

        active.set_metadata("startup_profile_id", profile["profile_id"])
        active.set_metadata("startup_base_pack", profile.get("base_pack", ""))
        active.set_metadata("startup_graph_id", profile.get("graph_id", ""))
        active.set_metadata("startup_packs", list(profile.get("packs", [])))
        active.set_metadata("startup_node_overrides", dict(profile.get("node_overrides", {})))
        active.set_metadata("startup_launched", bool(launched))
        active.set_metadata("startup_launch_requested_at", _now_ts() if launched else None)

        runtime_bindings = self._resolve_runtime_component_bindings(profile, catalog)
        active.set_metadata("startup_port_resolutions", runtime_bindings["port_resolutions"])
        active.set_metadata("startup_component_overrides", runtime_bindings["component_overrides"])

        base_pack = profile.get("base_pack", "")
        if base_pack:
            active.set_interface_override("rumiai.startup.base_pack", base_pack)

        for port_key, binding in runtime_bindings["port_resolutions"].items():
            active.set_interface_override(f"rumiai.port.{port_key}", binding.get("resolved_node", ""))

        managed_component_types = sorted(runtime_bindings["component_overrides"].keys())
        for component_type in managed_component_types:
            selected_component = runtime_bindings["component_overrides"].get(component_type, "")
            if selected_component:
                active.set_override(component_type, selected_component)
            else:
                active.remove_override(component_type)

    def _resolve_runtime_component_bindings(
        self,
        profile: Dict[str, Any],
        catalog: Dict[str, Any],
    ) -> Dict[str, Any]:
        component_overrides: Dict[str, str] = {}
        port_resolutions: Dict[str, Dict[str, Any]] = {}
        conflicts: List[Dict[str, str]] = []
        binding_sources: Dict[str, str] = {}

        graph_ports = profile.get("graph_ports", [])
        node_overrides = profile.get("node_overrides", {})
        base_pack = profile.get("base_pack", "")

        node_catalog = self._list_available_nodes(profile.get("packs", []), catalog)
        node_ref_map = {n["ref"]: n for n in node_catalog}

        for port in graph_ports:
            port_key = port["port_key"]
            override_node_ref = node_overrides.get(port_key)

            if override_node_ref and override_node_ref in node_ref_map:
                resolved_ref = override_node_ref
            else:
                resolved_ref = str(port.get("source_node_ref") or "")

            node_info = node_ref_map.get(resolved_ref, {})
            component_type = str(node_info.get("component_type") or "")
            component_id = str(node_info.get("component_id") or "")
            component_full_id = (
                f"{node_info.get('pack_id', base_pack)}:{component_type}:{component_id}"
                if component_type and component_id
                else ""
            )

            port_resolutions[port_key] = {
                "resolved_node": resolved_ref,
                "component_type": component_type,
                "component_full_id": component_full_id,
                "is_override": port_key in node_overrides,
            }

            if component_type and component_full_id:
                existing = component_overrides.get(component_type)
                if existing and existing != component_full_id:
                    conflicts.append({
                        "component_type": component_type,
                        "port_key": port_key,
                        "existing_component_full_id": existing,
                        "new_component_full_id": component_full_id,
                    })
                    continue
                component_overrides[component_type] = component_full_id
                binding_sources[component_type] = port_key

        return {
            "component_overrides": component_overrides,
            "port_resolutions": port_resolutions,
            "conflicts": conflicts,
        }

    # ------------------------------------------------------------------
    # Launch handoff
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Pack discovery
    # ------------------------------------------------------------------

    def _discover_packs(self) -> Dict[str, Dict[str, Any]]:
        discovered: Dict[str, Dict[str, Any]] = {}
        enabled_overrides = self._read_pack_enabled_overrides()
        for loc in discover_pack_locations(self.ecosystem_dir):
            try:
                ecosystem = json.loads(loc.ecosystem_json_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            default_enabled = bool(ecosystem.get("enabled", True))
            enabled = bool(enabled_overrides.get(loc.pack_id, default_enabled))
            approval_issues = self._approval_runtime_issues(loc.pack_id)
            discovered[loc.pack_id] = {
                "pack_id": loc.pack_id,
                "pack_identity": str(ecosystem.get("pack_identity", "")),
                "name": str(ecosystem.get("metadata", {}).get("name", loc.pack_id)),
                "description": str(ecosystem.get("metadata", {}).get("description", "")),
                "enabled": enabled,
                "approval_issues": approval_issues,
                "pack_subdir": loc.pack_subdir,
            }
        return discovered

    def _approval_runtime_issues(self, pack_id: str) -> List[str]:
        try:
            from .approval_manager import get_approval_manager
        except Exception:
            logger.debug("approval manager import is unavailable", exc_info=True)
            return []

        try:
            approval_manager = get_approval_manager()
        except Exception:
            logger.debug("failed to load approval manager", exc_info=True)
            return []

        if approval_manager is None or not hasattr(approval_manager, "get_approval"):
            return []

        try:
            approval = approval_manager.get_approval(pack_id)
        except Exception:
            logger.debug("failed to read pack approval for '%s'", pack_id, exc_info=True)
            return []

        if approval is None:
            return []

        try:
            approved, reason = approval_manager.is_pack_approved_and_verified(pack_id)
        except Exception:
            logger.debug("failed to verify pack approval for '%s'", pack_id, exc_info=True)
            return []

        if approved:
            return []

        reason_key = str(reason or "").strip().lower()
        if reason_key in {"modified", "hash_mismatch"}:
            return [f"Pack '{pack_id}' changed since it was last approved. Re-approve it before launching."]
        if reason_key == "blocked":
            return [f"Pack '{pack_id}' is blocked and cannot be launched."]
        if reason_key in {"not_approved", "not_found"}:
            return [f"Pack '{pack_id}' needs approval before it can be launched."]
        return [f"Pack '{pack_id}' is not ready for launch."]

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

    # ------------------------------------------------------------------
    # Runtime profile fields
    # ------------------------------------------------------------------

    def _runtime_profile_fields(self, profile_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        display_name = payload.get("display_name")
        if isinstance(display_name, str):
            display_name = {"en": display_name}
        if not isinstance(display_name, dict):
            name = str(payload.get("name") or profile_id)
            display_name = {"en": name, "ja": name}

        surfaces = payload.get("surfaces")
        if not isinstance(surfaces, dict):
            surfaces = {"preferred": "desktop", "enabled": ["desktop", "cli"]}
        node_settings = payload.get("node_settings")
        policy = payload.get("policy")
        permissions = payload.get("permissions")

        return {
            "kind": str(payload.get("kind") or "runtime_profile"),
            "display_name": {str(key): str(value) for key, value in display_name.items() if key and value},
            "locale": payload.get("locale") if isinstance(payload.get("locale"), str) else "ja",
            "default_flow": payload.get("default_flow") if isinstance(payload.get("default_flow"), str) else None,
            "default_graph": payload.get("default_graph") if isinstance(payload.get("default_graph"), str) else None,
            "capability_profile_id": (
                payload.get("capability_profile_id") if isinstance(payload.get("capability_profile_id"), str) else None
            ),
            "launch_capability_graph": bool(payload.get("launch_capability_graph", False)),
            "last_runtime_profile_key": (
                payload.get("last_runtime_profile_key")
                if isinstance(payload.get("last_runtime_profile_key"), str)
                else payload.get("runtime_profile_key")
                if isinstance(payload.get("runtime_profile_key"), str)
                else None
            ),
            "surfaces": dict(surfaces),
            "enabled_nodes": self._string_list(payload.get("enabled_nodes")),
            "disabled_nodes": self._string_list(payload.get("disabled_nodes")),
            "node_settings": dict(node_settings) if isinstance(node_settings, dict) else {},
            "policy": dict(policy) if isinstance(policy, dict) else {},
            "permissions": dict(permissions) if isinstance(permissions, dict) else {},
        }

    def _runtime_profile_field_names(self) -> List[str]:
        return [
            "kind",
            "display_name",
            "locale",
            "default_flow",
            "default_graph",
            "capability_profile_id",
            "launch_capability_graph",
            "last_runtime_profile_key",
            "surfaces",
            "enabled_nodes",
            "disabled_nodes",
            "node_settings",
            "policy",
            "permissions",
        ]

    def _string_list(self, value: Any) -> List[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if isinstance(item, str) and item]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

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
