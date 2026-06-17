from __future__ import annotations

import importlib
from functools import lru_cache
from pathlib import Path
from typing import Any

from .manifest_factory import FunctionSpec, manifest_for


TRUST_BUILTIN = "builtin"
TEMPLATE_RUNTIME_ENTRYPOINT = "template_runner.py:run"


def _pack_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _runtime_dir() -> Path:
    return Path(__file__).resolve().parent


@lru_cache(maxsize=4)
def _template_catalog(defaultspack_root: str | None = None) -> dict[str, Any]:
    try:
        projectors = importlib.import_module("domain.templates.projectors")
        build_template_catalog = getattr(projectors, "build_template_catalog", None)
    except Exception:
        return {}
    if not callable(build_template_catalog):
        return {}
    try:
        catalog = build_template_catalog(defaultspack_root=defaultspack_root or _pack_root())
    except Exception:
        return {}
    return catalog if isinstance(catalog, dict) else {}


def template_function_specs(defaultspack_root: str | Path | None = None) -> dict[str, FunctionSpec]:
    root = str(defaultspack_root) if defaultspack_root is not None else None
    catalog = _template_catalog(root)
    specs: dict[str, FunctionSpec] = {}
    for item in _iter_template_function_items(catalog):
        spec = _spec_from_template_item(item)
        if spec is None or spec.function_id in specs:
            continue
        specs[spec.function_id] = spec
    return specs


def template_function_manifests(defaultspack_root: str | Path | None = None) -> dict[str, dict[str, Any]]:
    manifests: dict[str, dict[str, Any]] = {}
    for function_id, spec in template_function_specs(defaultspack_root).items():
        manifest = manifest_for(spec)
        manifest["entrypoint"] = TEMPLATE_RUNTIME_ENTRYPOINT
        manifest.setdefault("extensions", {}).setdefault("defaultspack", {})[
            "template_runtime"
        ] = True
        manifests[function_id] = manifest
    return manifests


def register_template_functions(registry: Any, defaultspack_root: str | Path | None = None) -> int:
    if registry is None:
        return 0
    registered = 0
    for function_id, manifest in template_function_manifests(defaultspack_root).items():
        try:
            if registry.register(
                pack_id="defaultspack",
                function_id=function_id,
                manifest=manifest,
                function_dir=_runtime_dir(),
            ):
                registered += 1
        except Exception:
            continue
    return registered


def template_route_items(defaultspack_root: str | Path | None = None) -> list[dict[str, Any]]:
    root = str(defaultspack_root) if defaultspack_root is not None else None
    items: list[dict[str, Any]] = []
    for item in _iter_template_function_items(_template_catalog(root)):
        if not _is_builtin_template_item(item):
            continue
        function_id = _function_id(item)
        method = str(item.get("method") or item.get("http_method") or "").strip().upper()
        route_path = str(item.get("route_path") or item.get("path") or "").strip()
        if not function_id or not method or not route_path.startswith("/"):
            continue
        block_module = _block_module_from_item(item)
        items.append(
            {
                "function_id": function_id,
                "method": method,
                "path": route_path,
                "block_module": block_module,
                "default_args": _default_args(item),
                "template_id": item.get("template_id"),
                "piece_id": item.get("piece_id"),
                "projected_id": item.get("projected_id"),
            }
        )
    return items


def _iter_template_function_items(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen_projected: set[str] = set()
    for key in ("actions", "data_sources"):
        values = catalog.get(key)
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict):
                continue
            projected_id = str(item.get("projected_id") or "").strip()
            if projected_id and projected_id in seen_projected:
                continue
            if projected_id:
                seen_projected.add(projected_id)
            items.append(item)
    return items


def _spec_from_template_item(item: dict[str, Any]) -> FunctionSpec | None:
    if not _is_builtin_template_item(item):
        return None
    function_id = _function_id(item)
    if not function_id:
        return None
    block_module = _block_module_from_item(item)
    handler_ref = _handler_ref(item)
    if block_module is None:
        return None
    role = str(item.get("role") or "").strip()
    risk = _risk(item, role=role)
    return FunctionSpec(
        function_id=function_id,
        description=_description(item, function_id),
        tags=_tags(item, role=role),
        risk=risk,
        block_module=block_module,
        handler_ref=handler_ref,
        default_args=_default_args(item),
        requires=_requires(item, function_id=function_id, risk=risk),
        caller_requires=_caller_requires(item, risk=risk),
        input_schema=_input_schema(item),
        permission_id=_permission_id(item),
    )


def _is_builtin_template_item(item: dict[str, Any]) -> bool:
    return str(item.get("trust_level") or "").strip().lower() == TRUST_BUILTIN


def _function_id(item: dict[str, Any]) -> str:
    return str(
        item.get("function_id")
        or item.get("action_id")
        or item.get("data_source")
        or item.get("id")
        or ""
    ).strip()


def _handler_ref(item: dict[str, Any]) -> str:
    return str(item.get("handler_ref") or item.get("handler") or "").strip()


def _block_module_from_item(item: dict[str, Any]) -> str | None:
    block_module = str(item.get("block_module") or "").strip()
    if block_module.startswith("blocks."):
        return block_module
    handler_ref = _handler_ref(item)
    if ":" not in handler_ref:
        return None
    module_name, _, callable_name = handler_ref.partition(":")
    module_name = module_name.strip()
    callable_name = callable_name.strip()
    if module_name.startswith("blocks.") and callable_name == "run":
        return module_name
    return None


def _default_args(item: dict[str, Any]) -> dict[str, Any]:
    value = item.get("default_args")
    return dict(value) if isinstance(value, dict) else {}


def _risk(item: dict[str, Any], *, role: str) -> str:
    raw = str(item.get("risk") or "").strip().lower()
    if raw in {"low", "medium", "high"}:
        return raw
    if item.get("requires_approval") is True:
        return "high"
    return "low" if role == "data_source" else "medium"


def _description(item: dict[str, Any], function_id: str) -> str:
    for key in ("description", "returns", "label"):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return f"Template-backed defaultspack function {function_id}."


def _tags(item: dict[str, Any], *, role: str) -> tuple[str, ...]:
    tags = ["template"]
    if role:
        tags.append(role)
    template_id = str(item.get("template_id") or "").strip()
    if template_id:
        tags.append(template_id)
    return tuple(dict.fromkeys(tags))


def _requires(item: dict[str, Any], *, function_id: str, risk: str) -> tuple[str, ...]:
    permission_id = _permission_id(item)
    if permission_id:
        return (permission_id,) if risk != "low" else ()
    if risk == "low":
        return ()
    namespace, _, operation = function_id.partition("_")
    permission = f"{namespace}.{operation.replace('_', '.')}" if operation else namespace
    return (permission,)


def _caller_requires(item: dict[str, Any], *, risk: str) -> tuple[str, ...]:
    value = item.get("caller_requires")
    if isinstance(value, list):
        return tuple(str(entry) for entry in value if str(entry or "").strip())
    if risk == "high":
        return ("user.approved.high_risk",)
    return ()


def _input_schema(item: dict[str, Any]) -> dict[str, Any] | None:
    value = item.get("input_schema")
    return dict(value) if isinstance(value, dict) else None


def _permission_id(item: dict[str, Any]) -> str | None:
    value = str(item.get("permission_id") or "").strip()
    return value or None
