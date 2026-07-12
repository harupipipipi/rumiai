from __future__ import annotations

import json
from typing import Any, Iterable


def canonical_json(value: Any, *, ensure_ascii: bool = True) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=ensure_ascii,
    )


def string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [item.strip() for item in value.split(",")]
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def ordered_unique_strings(values: Iterable[Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


def sorted_unique_strings(values: Iterable[Any]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value or "").strip()})


def payload_source(item: dict[str, Any], *nested_keys: str) -> dict[str, Any]:
    for key in nested_keys:
        nested = item.get(key)
        if isinstance(nested, dict):
            return nested
    return item
