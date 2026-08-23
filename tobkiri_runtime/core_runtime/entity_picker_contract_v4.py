"""Finite Host normalization for Pack v4 entity-picker contracts."""

from __future__ import annotations

import re
from typing import Any, Mapping


ENTITY_PICKER_ACTION_CONTRACT = "rumi.action.entity-picker.v1"
ENTITY_PICKER_DATA_SOURCE_CONTRACT = "tobkiri.data.entity-picker.v1"
ENTITY_PICKER_CONTRACTS = frozenset(
    {ENTITY_PICKER_ACTION_CONTRACT, ENTITY_PICKER_DATA_SOURCE_CONTRACT}
)

_ENTITY_PICKER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_ENTITY_PICKER_SCOPES = frozenset(
    {"draft", "conversation", "run", "settings", "workspace", "global"}
)
_ENTITY_PICKER_INPUT_KEYS = frozenset(
    {
        "picker_id",
        "selected_ids",
        "data_source_id",
        "source_revision",
        "value_scope",
        "query",
        "cursor",
    }
)


def entity_picker_input_keys() -> frozenset[str]:
    """Return the browser-supplied keys accepted by entity-picker contracts."""

    return _ENTITY_PICKER_INPUT_KEYS


def normalize_entity_picker_input(
    contract_id: str,
    value: Mapping[str, Any],
    *,
    profile_id: str,
) -> dict[str, Any]:
    """Validate picker input and inject the authoritative Profile identity."""

    if contract_id not in ENTITY_PICKER_CONTRACTS:
        raise ValueError("entity picker contract is unsupported")
    if set(value) - _ENTITY_PICKER_INPUT_KEYS:
        raise ValueError("entity picker input contains unknown fields")
    for field in ("picker_id", "data_source_id"):
        if _ENTITY_PICKER_ID.fullmatch(str(value.get(field) or "")) is None:
            raise ValueError(f"entity picker {field} is invalid")
    normalized = dict(value)
    if "selected_ids" in value:
        selected = value["selected_ids"]
        if not isinstance(selected, list) or len(selected) > 100:
            raise ValueError("entity picker selected_ids is invalid")
        normalized_selected = [str(item) for item in selected]
        if (
            len(set(normalized_selected)) != len(normalized_selected)
            or any(
                _ENTITY_PICKER_ID.fullmatch(item) is None
                for item in normalized_selected
            )
        ):
            raise ValueError("entity picker selected_ids is invalid")
        normalized["selected_ids"] = normalized_selected
    scope = value.get("value_scope")
    if scope is not None and str(scope) not in _ENTITY_PICKER_SCOPES:
        raise ValueError("entity picker value_scope is invalid")
    for field, limit in (("source_revision", 160), ("query", 500), ("cursor", 200)):
        field_value = value.get(field)
        if field_value is not None and (
            not isinstance(field_value, str) or len(field_value) > limit
        ):
            raise ValueError(f"entity picker {field} is invalid")
    normalized["profile_id"] = profile_id
    return normalized


__all__ = [
    "ENTITY_PICKER_ACTION_CONTRACT",
    "ENTITY_PICKER_CONTRACTS",
    "ENTITY_PICKER_DATA_SOURCE_CONTRACT",
    "entity_picker_input_keys",
    "normalize_entity_picker_input",
]
