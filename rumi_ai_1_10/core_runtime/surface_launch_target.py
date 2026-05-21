"""Resolve user-facing startup surface launch targets from runtime profiles."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional


def extract_surface_launch_target(
    runtime_profile: Optional[Dict[str, Any]],
    *,
    fallback_pack_id: Optional[str],
    surfaces: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Return the canonical surface launch target for a compiled runtime profile."""
    if not isinstance(runtime_profile, dict):
        return normalize_surface_launch_target(
            None,
            fallback_pack_id=fallback_pack_id,
            surfaces=surfaces,
        )

    explicit = normalize_surface_launch_target(
        _nested_dict(runtime_profile, "launch", "surface"),
        fallback_pack_id=None,
        surfaces=surfaces,
    )
    if explicit:
        return explicit

    target = _from_defaultspack_frontend_surface(runtime_profile, surfaces=surfaces)
    if target:
        return target

    target = _from_launch_metadata_nodes(runtime_profile, surfaces=surfaces)
    if target:
        return target

    return normalize_surface_launch_target(
        None,
        fallback_pack_id=fallback_pack_id,
        surfaces=surfaces,
    )


def normalize_surface_launch_target(
    target: Any,
    *,
    fallback_pack_id: Optional[str],
    surfaces: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Normalize a stored launch target, falling back to a pack launch when needed."""
    if isinstance(target, Mapping):
        normalized = _normalize_target_mapping(target, surfaces=surfaces)
        if normalized:
            return normalized

    pack_id = _clean_string(fallback_pack_id)
    if not pack_id:
        return None
    mode = resolve_surface_mode(surfaces)
    return {
        "kind": "desktop_app",
        "pack_id": pack_id,
        "principal_id": pack_id,
        "surface": mode,
        "env": surface_env(mode),
        "source": "startup_profile_fallback",
    }


def surface_launch_target_from_instance(
    *,
    runtime_profile: Dict[str, Any],
    instance: Any,
    nodes: Dict[str, Any],
    profile: Any = None,
    surfaces: Optional[Dict[str, Any]] = None,
    diagnostics: Optional[list[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """Build a launch target for the graph node instance that provides a surface."""
    del profile
    node_id = _clean_string(getattr(instance, "ref", None))
    node_instance_id = _clean_string(getattr(instance, "id", None))
    node = nodes.get(node_id) if isinstance(nodes, dict) else None
    node_payload = _node_to_mapping(node)
    if not node_payload:
        node_payload = _runtime_node_payload(runtime_profile, node_instance_id).get("node") or {}
    return _target_from_node_payload(
        node_payload,
        node_instance_id=node_instance_id,
        node_id=node_id,
        surfaces=surfaces,
        diagnostics=diagnostics,
    )


def resolve_surface_mode(surfaces: Any) -> str:
    if not isinstance(surfaces, dict):
        return "browser"
    preferred = str(surfaces.get("preferred") or "").strip().lower()
    enabled = {
        str(surface).strip().lower()
        for surface in surfaces.get("enabled", [])
        if isinstance(surface, str)
    }
    if preferred in {"desktop", "webview", "native"}:
        return "desktop"
    if preferred in {"browser", "web"}:
        return "browser"
    if "desktop" in enabled and "browser" not in enabled and "web" not in enabled:
        return "desktop"
    return "browser"


def surface_env(mode: str) -> Dict[str, str]:
    normalized = "desktop" if str(mode).strip().lower() == "desktop" else "browser"
    env = {
        "RUMI_PROFILE_SURFACE": normalized,
        "RUMI_DEFAULTSPACK_OPEN_BROWSER": "1",
    }
    if normalized == "desktop":
        env["RUMI_DEFAULTSPACK_SURFACE"] = "webview"
    else:
        env["RUMI_DEFAULTSPACK_SURFACE"] = "browser"
    return env


def _from_defaultspack_frontend_surface(
    runtime_profile: Dict[str, Any],
    *,
    surfaces: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    defaultspack = runtime_profile.get("defaultspack")
    if not isinstance(defaultspack, dict):
        return None
    frontends = defaultspack.get("frontends")
    if not isinstance(frontends, dict):
        return None
    for frontend in frontends.values():
        if not isinstance(frontend, dict):
            continue
        explicit = normalize_surface_launch_target(
            frontend.get("surface_launch_target"),
            fallback_pack_id=None,
            surfaces=surfaces,
        )
        if explicit:
            return explicit
        refs = []
        if isinstance(frontend.get("surface"), str):
            refs.append(frontend["surface"])
        refs.extend(item for item in frontend.get("surfaces", []) if isinstance(item, str))
        for node_instance_id in refs:
            target = _target_from_runtime_node_instance(
                runtime_profile,
                node_instance_id=node_instance_id,
                surfaces=surfaces,
                diagnostics=None,
            )
            if target:
                return target
    return None


def _from_launch_metadata_nodes(
    runtime_profile: Dict[str, Any],
    *,
    surfaces: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    runtime_nodes = runtime_profile.get("nodes")
    if not isinstance(runtime_nodes, dict):
        return None
    for node_instance_id in sorted(runtime_nodes):
        payload = runtime_nodes.get(node_instance_id)
        if not isinstance(payload, dict):
            continue
        node = payload.get("node")
        if not isinstance(node, dict):
            continue
        launch = node.get("metadata", {}).get("launch") if isinstance(node.get("metadata"), dict) else None
        if not isinstance(launch, dict) or launch.get("default") is not True:
            continue
        target = _target_from_node_payload(
            node,
            node_instance_id=node_instance_id,
            node_id=_clean_string(payload.get("node_id") or node.get("node_id")),
            surfaces=surfaces,
            diagnostics=None,
        )
        if target:
            return target
    return None


def _target_from_runtime_node_instance(
    runtime_profile: Dict[str, Any],
    *,
    node_instance_id: str,
    surfaces: Optional[Dict[str, Any]],
    diagnostics: Optional[list[Dict[str, Any]]],
) -> Optional[Dict[str, Any]]:
    payload = _runtime_node_payload(runtime_profile, node_instance_id)
    node = payload.get("node")
    if not isinstance(node, dict):
        return None
    return _target_from_node_payload(
        node,
        node_instance_id=node_instance_id,
        node_id=_clean_string(payload.get("node_id") or node.get("node_id")),
        surfaces=surfaces,
        diagnostics=diagnostics,
    )


def _target_from_node_payload(
    node_payload: Mapping[str, Any],
    *,
    node_instance_id: str,
    node_id: str,
    surfaces: Optional[Dict[str, Any]],
    diagnostics: Optional[list[Dict[str, Any]]],
) -> Optional[Dict[str, Any]]:
    metadata = node_payload.get("metadata")
    if not isinstance(metadata, Mapping):
        metadata = {}
    launch = metadata.get("launch")
    if launch is None:
        launch = {}
    if not isinstance(launch, Mapping):
        return None
    kind = _clean_string(launch.get("kind") or "desktop_app")
    if kind != "desktop_app":
        return None

    node_pack_id = _clean_string(metadata.get("pack_id")) or _node_pack_id(node_id)
    target_pack_id = _clean_string(launch.get("pack_id")) or node_pack_id
    if not node_pack_id or not target_pack_id:
        return None
    if target_pack_id != node_pack_id:
        _diagnose(
            diagnostics,
            "error",
            "launch_pack_mismatch",
            "Surface node launch target pack does not match the node pack",
            node_id=node_id,
            node_instance_id=node_instance_id,
            node_pack_id=node_pack_id,
            launch_pack_id=target_pack_id,
        )
        return None

    principal_id = _clean_string(launch.get("principal_id")) or target_pack_id
    if principal_id != target_pack_id:
        _diagnose(
            diagnostics,
            "error",
            "launch_principal_mismatch",
            "Surface node launch principal must match the target pack",
            node_id=node_id,
            node_instance_id=node_instance_id,
            principal_id=principal_id,
            launch_pack_id=target_pack_id,
        )
        return None

    mode = _clean_string(launch.get("surface")) or resolve_surface_mode(surfaces)
    env = surface_env(mode)
    env.update(_string_dict(launch.get("env")))
    target: Dict[str, Any] = {
        "kind": "desktop_app",
        "pack_id": target_pack_id,
        "principal_id": principal_id,
        "surface": mode,
        "node_instance_id": node_instance_id,
        "node_id": node_id,
        "env": env,
        "source": "capability_graph",
    }
    component_full_id = _component_full_id(metadata, target_pack_id)
    if component_full_id:
        target["component_full_id"] = component_full_id
    return target


def _normalize_target_mapping(
    target: Mapping[str, Any],
    *,
    surfaces: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    kind = _clean_string(target.get("kind") or "desktop_app")
    if kind != "desktop_app":
        return None
    pack_id = _clean_string(target.get("pack_id"))
    if not pack_id:
        return None
    principal_id = _clean_string(target.get("principal_id")) or pack_id
    mode = _clean_string(target.get("surface")) or resolve_surface_mode(surfaces)
    env = surface_env(mode)
    env.update(_string_dict(target.get("env")))
    normalized: Dict[str, Any] = {
        "kind": "desktop_app",
        "pack_id": pack_id,
        "principal_id": principal_id,
        "surface": mode,
        "env": env,
        "source": _clean_string(target.get("source")) or "capability_graph",
    }
    for key in ("node_instance_id", "node_id", "component_full_id"):
        value = _clean_string(target.get(key))
        if value:
            normalized[key] = value
    return normalized


def _runtime_node_payload(runtime_profile: Dict[str, Any], node_instance_id: str) -> Dict[str, Any]:
    runtime_nodes = runtime_profile.get("nodes")
    if not isinstance(runtime_nodes, dict):
        return {}
    payload = runtime_nodes.get(node_instance_id)
    return dict(payload) if isinstance(payload, dict) else {}


def _node_to_mapping(node: Any) -> Dict[str, Any]:
    if isinstance(node, Mapping):
        return dict(node)
    to_dict = getattr(node, "to_dict", None)
    if callable(to_dict):
        value = to_dict()
        return dict(value) if isinstance(value, Mapping) else {}
    return {}


def _nested_dict(data: Dict[str, Any], *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _node_pack_id(node_id: str) -> str:
    return node_id.split(".", 1)[0] if "." in node_id else ""


def _component_full_id(metadata: Mapping[str, Any], pack_id: str) -> str:
    explicit = _clean_string(metadata.get("component_full_id"))
    if explicit:
        return explicit
    component_type = _clean_string(metadata.get("component_type") or metadata.get("component"))
    component_id = _clean_string(metadata.get("component_id"))
    if component_type and component_id:
        return f"{pack_id}:{component_type}:{component_id}"
    return ""


def _string_dict(value: Any) -> Dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    result: Dict[str, str] = {}
    for key, item in value.items():
        if isinstance(key, str) and key:
            result[key] = str(item)
    return result


def _clean_string(value: Any) -> str:
    return str(value).strip() if isinstance(value, str) and value.strip() else ""


def _diagnose(
    diagnostics: Optional[list[Dict[str, Any]]],
    level: str,
    code: str,
    message: str,
    **meta: Any,
) -> None:
    if diagnostics is None:
        return
    diagnostics.append(
        {
            "level": level,
            "code": code,
            "message": message,
            **meta,
        }
    )
