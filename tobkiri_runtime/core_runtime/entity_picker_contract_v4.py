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
_ENTITY_PICKER_ACTION_KEYS = frozenset(
    {"picker_id", "selected_ids", "data_source_id", "source_revision", "value_scope"}
)
_ENTITY_PICKER_DATA_SOURCE_KEYS = frozenset(
    {"picker_id", "data_source_id", "source_revision", "query", "cursor"}
)


def entity_picker_input_keys(contract_id: str) -> frozenset[str]:
    """Return browser-supplied keys for one entity-picker contract stage."""

    if contract_id == ENTITY_PICKER_ACTION_CONTRACT:
        return _ENTITY_PICKER_ACTION_KEYS
    if contract_id == ENTITY_PICKER_DATA_SOURCE_CONTRACT:
        return _ENTITY_PICKER_DATA_SOURCE_KEYS
    raise ValueError("entity picker contract is unsupported")


def normalize_entity_picker_input(
    contract_id: str,
    value: Mapping[str, Any],
    *,
    profile_id: str,
) -> dict[str, Any]:
    """Validate picker input and inject the authoritative Profile identity."""

    if contract_id not in ENTITY_PICKER_CONTRACTS:
        raise ValueError("entity picker contract is unsupported")
    allowed_keys = entity_picker_input_keys(contract_id)
    if set(value) - allowed_keys:
        raise ValueError("entity picker input contains unknown fields")
    if contract_id == ENTITY_PICKER_ACTION_CONTRACT and not {
        "selected_ids",
        "value_scope",
    }.issubset(value):
        raise ValueError("entity picker action input is incomplete")
    for field in ("picker_id", "data_source_id"):
        field_value = value.get(field)
        if (
            not isinstance(field_value, str)
            or _ENTITY_PICKER_ID.fullmatch(field_value) is None
        ):
            raise ValueError(f"entity picker {field} is invalid")
    normalized = dict(value)
    if contract_id == ENTITY_PICKER_ACTION_CONTRACT:
        selected = value["selected_ids"]
        if not isinstance(selected, list) or len(selected) > 100:
            raise ValueError("entity picker selected_ids is invalid")
        if (
            any(not isinstance(item, str) for item in selected)
            or len(set(selected)) != len(selected)
            or any(
                _ENTITY_PICKER_ID.fullmatch(item) is None
                for item in selected
            )
        ):
            raise ValueError("entity picker selected_ids is invalid")
        normalized["selected_ids"] = list(selected)
    scope = value.get("value_scope")
    if contract_id == ENTITY_PICKER_ACTION_CONTRACT and (
        not isinstance(scope, str) or scope not in _ENTITY_PICKER_SCOPES
    ):
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
