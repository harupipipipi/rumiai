from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from .projectors import build_template_catalog


_TEMPLATE_POLICY_AUTHORITY_FIELDS = {
    "allowedToolIds",
    "allowed_tool_ids",
    "allowed_tools",
    "allowlist",
    "defaultDisabledTools",
    "defaultEnabledTools",
    "default_disabled_tools",
    "default_enabled_tools",
    "deniedToolIds",
    "denied_tool_ids",
    "denied_tools",
    "denylist",
    "tool_allowlist",
    "tool_blocklist",
    "tool_denylist",
}
_AI_INPUT_ID_KEYS = ("ai_input_id", "template_ai_input_id", "ai_input")
_TOOL_POLICY_ID_KEYS = ("template_tool_policy_id", "tool_policy_id")
_ALLOWLIST_KEYS = ("tool_allowlist", "allowed_tools", "allowlist", "allowed_tool_ids", "allowedToolIds")
_DENYLIST_KEYS = ("tool_denylist", "denied_tools", "denylist", "denied_tool_ids", "deniedToolIds", "tool_blocklist")
_DISABLED_KEYS = ("disabled_tools",)
_DEFAULT_ENABLED_KEYS = ("default_enabled_tools", "defaultEnabledTools")
_DEFAULT_DISABLED_KEYS = ("default_disabled_tools", "defaultDisabledTools")
_TOOL_CHOICE_VALUES = {"auto", "none", "required"}


@dataclass
class TemplateToolPolicyResolution:
    policy: dict[str, Any]
    id_requested: bool = False
    catalog_available: bool = False
    applied: bool = False
    requested_ai_input_id: str = ""
    requested_template_tool_policy_id: str = ""
    resolved_ai_input_id: str = ""
    resolved_template_tool_policy_id: str = ""
    diagnostics: list[dict[str, Any]] = field(default_factory=list)

    def to_context(self) -> dict[str, Any]:
        return {
            "id_requested": self.id_requested,
            "catalog_available": self.catalog_available,
            "applied": self.applied,
            "requested_ai_input_id": self.requested_ai_input_id or None,
            "requested_template_tool_policy_id": self.requested_template_tool_policy_id or None,
            "resolved_ai_input_id": self.resolved_ai_input_id or None,
            "resolved_template_tool_policy_id": self.resolved_template_tool_policy_id or None,
            "diagnostics": [dict(item) for item in self.diagnostics],
        }


def resolve_template_tool_policy(
    request_policy: dict[str, Any] | None,
    *,
    metadata: dict[str, Any] | None = None,
    catalog: dict[str, Any] | None = None,
    defaultspack_root: str | Path | None = None,
) -> TemplateToolPolicyResolution:
    """Resolve request template ids to an authoritative backend tool policy."""
    raw_policy = deepcopy(request_policy) if isinstance(request_policy, dict) else {}
    requested_ai_input_id = _first_non_empty(raw_policy, metadata, keys=_AI_INPUT_ID_KEYS)
    requested_policy_id = _first_non_empty(raw_policy, metadata, keys=_TOOL_POLICY_ID_KEYS)
    id_requested = bool(requested_ai_input_id or requested_policy_id)
    if not id_requested:
        return TemplateToolPolicyResolution(policy=raw_policy)

    loaded_catalog = catalog if isinstance(catalog, dict) else _load_template_catalog(defaultspack_root)
    if not _catalog_has_template_policy_surface(loaded_catalog):
        return TemplateToolPolicyResolution(
            policy=raw_policy,
            id_requested=True,
            requested_ai_input_id=requested_ai_input_id,
            requested_template_tool_policy_id=requested_policy_id,
        )

    diagnostics: list[dict[str, Any]] = []
    resolved_ai_input: dict[str, Any] | None = None
    if requested_ai_input_id:
        resolved_ai_input = _find_catalog_item(loaded_catalog.get("ai_inputs"), requested_ai_input_id)
        if resolved_ai_input is None:
            diagnostics.append(_diagnostic("template_ai_input_not_found", requested_ai_input_id))

    policy_ids = _candidate_policy_ids(resolved_ai_input)
    if requested_policy_id:
        policy_ids.append(requested_policy_id)

    resolved_policy: dict[str, Any] | None = None
    for policy_id in _dedupe(policy_ids):
        resolved_policy = _find_catalog_item(loaded_catalog.get("tool_policies"), policy_id)
        if resolved_policy is not None:
            break

    if resolved_ai_input is not None and requested_policy_id:
        ai_policy_ids = set(_candidate_policy_ids(resolved_ai_input))
        if ai_policy_ids and requested_policy_id not in ai_policy_ids and not _catalog_item_matches(resolved_policy, requested_policy_id):
            diagnostics.append(_diagnostic("template_tool_policy_mismatch", requested_policy_id))

    if resolved_policy is None:
        if requested_policy_id:
            diagnostics.append(_diagnostic("template_tool_policy_not_found", requested_policy_id))
        return TemplateToolPolicyResolution(
            policy=_strip_template_authority_fields(raw_policy),
            id_requested=True,
            catalog_available=True,
            requested_ai_input_id=requested_ai_input_id,
            requested_template_tool_policy_id=requested_policy_id,
            resolved_ai_input_id=str((resolved_ai_input or {}).get("id") or ""),
            diagnostics=diagnostics,
        )

    request_disabled_tools = _first_string_list(raw_policy, _DISABLED_KEYS)
    policy = _strip_template_authority_fields(raw_policy)
    materialized_policy = _materialize_template_policy(resolved_policy)
    if request_disabled_tools:
        materialized_policy["tool_denylist"] = _dedupe(
            [
                *materialized_policy.get("tool_denylist", []),
                *request_disabled_tools,
            ]
        )
    policy.update(materialized_policy)
    if requested_ai_input_id:
        policy["ai_input_id"] = requested_ai_input_id
    policy["template_tool_policy_id"] = str(resolved_policy.get("id") or requested_policy_id or "")
    policy["template_tool_policy_projected_id"] = str(resolved_policy.get("projected_id") or "")

    return TemplateToolPolicyResolution(
        policy=policy,
        id_requested=True,
        catalog_available=True,
        applied=True,
        requested_ai_input_id=requested_ai_input_id,
        requested_template_tool_policy_id=requested_policy_id,
        resolved_ai_input_id=str((resolved_ai_input or {}).get("id") or ""),
        resolved_template_tool_policy_id=str(resolved_policy.get("id") or ""),
        diagnostics=diagnostics,
    )


@lru_cache(maxsize=4)
def _cached_template_catalog(defaultspack_root: str) -> dict[str, Any] | None:
    try:
        return build_template_catalog(defaultspack_root=defaultspack_root)
    except Exception:
        return None


def _load_template_catalog(defaultspack_root: str | Path | None) -> dict[str, Any] | None:
    root = Path(defaultspack_root) if defaultspack_root is not None else Path(__file__).resolve().parents[2]
    return _cached_template_catalog(str(root))


def _catalog_has_template_policy_surface(catalog: dict[str, Any] | None) -> bool:
    if not isinstance(catalog, dict):
        return False
    return bool(catalog.get("tool_policies"))


def _first_non_empty(*sources: dict[str, Any] | None, keys: tuple[str, ...]) -> str:
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in keys:
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if value not in (None, "", [], {}) and not isinstance(value, (dict, list)):
                return str(value).strip()
    return ""


def _find_catalog_item(items: Any, requested_id: str) -> dict[str, Any] | None:
    requested = str(requested_id or "").strip()
    if not requested or not isinstance(items, list):
        return None
    for item in items:
        if _catalog_item_matches(item, requested):
            return item
    return None


def _catalog_item_matches(item: Any, requested_id: str) -> bool:
    if not isinstance(item, dict) or item.get("enabled") is False:
        return False
    requested = str(requested_id or "").strip()
    if not requested:
        return False
    keys = {
        str(item.get(key) or "").strip()
        for key in (
            "id",
            "projected_id",
            "piece_id",
            "policy_id",
            "tool_policy_id",
            "ai_input_id",
            "input_id",
        )
        if str(item.get(key) or "").strip()
    }
    template_id = str(item.get("template_id") or "").strip()
    piece_id = str(item.get("piece_id") or "").strip()
    item_id = str(item.get("id") or "").strip()
    if template_id and piece_id:
        keys.add(f"{template_id}:{piece_id}")
    if template_id and item_id:
        keys.add(f"{template_id}:{item_id}")
    return requested in keys


def _candidate_policy_ids(ai_input: dict[str, Any] | None) -> list[str]:
    if not isinstance(ai_input, dict):
        return []
    source = _payload_source(ai_input, "input", "ai_input")
    return _string_list(source.get("tool_policy_id") or source.get("tool_policy"))


def _payload_source(item: dict[str, Any], *nested_keys: str) -> dict[str, Any]:
    for key in nested_keys:
        nested = item.get(key)
        if isinstance(nested, dict):
            return nested
    return item


def _strip_template_authority_fields(policy: dict[str, Any]) -> dict[str, Any]:
    return {key: deepcopy(value) for key, value in policy.items() if key not in _TEMPLATE_POLICY_AUTHORITY_FIELDS}


def _materialize_template_policy(catalog_policy: dict[str, Any]) -> dict[str, Any]:
    source = _payload_source(catalog_policy, "policy", "tool_policy")
    materialized: dict[str, Any] = {}
    allowlist, has_allowlist = _first_string_list_with_presence(source, _ALLOWLIST_KEYS)
    denylist = _dedupe(
        [
            *_first_string_list(source, _DENYLIST_KEYS),
            *_first_string_list(source, _DISABLED_KEYS),
            *_first_string_list(source, _DEFAULT_DISABLED_KEYS),
        ]
    )
    default_enabled = _first_string_list(source, _DEFAULT_ENABLED_KEYS)
    default_disabled = _first_string_list(source, _DEFAULT_DISABLED_KEYS)
    selected_tools = _first_string_list(source, ("selected_tools",))
    if has_allowlist:
        materialized["tool_allowlist"] = allowlist
    if denylist:
        materialized["tool_denylist"] = denylist
    if default_enabled:
        materialized["default_enabled_tools"] = default_enabled
    if default_disabled:
        materialized["default_disabled_tools"] = default_disabled
    if selected_tools:
        materialized["selected_tools"] = selected_tools
    for key in ("toggleable", "parallel_tool_calls"):
        if isinstance(source.get(key), bool):
            materialized[key] = source[key]
    tool_choice = _valid_tool_choice(source.get("tool_choice"))
    if tool_choice is not None:
        materialized["tool_choice"] = tool_choice
    params = source.get("params")
    if isinstance(params, dict):
        materialized["params"] = deepcopy(params)
    return materialized


def _first_string_list(source: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    for key in keys:
        if key in source:
            values = _string_list(source.get(key))
            if values:
                return values
    return []


def _first_string_list_with_presence(source: dict[str, Any], keys: tuple[str, ...]) -> tuple[list[str], bool]:
    for key in keys:
        if key in source:
            return _string_list(source.get(key)), True
    return [], False


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [item.strip() for item in value.split(",")]
    if not isinstance(value, list):
        return []
    return _dedupe(str(item).strip() for item in value if str(item or "").strip())


def _dedupe(values: Any) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


def _valid_tool_choice(value: Any) -> Any:
    if isinstance(value, str):
        normalized = value.strip().lower()
        return normalized if normalized in _TOOL_CHOICE_VALUES else None
    if isinstance(value, dict):
        return deepcopy(value)
    return None


def _diagnostic(code: str, requested_id: str) -> dict[str, Any]:
    return {
        "level": "warning",
        "severity": "warning",
        "code": f"template.tool_policy_resolution.{code}",
        "requested_id": requested_id,
    }
