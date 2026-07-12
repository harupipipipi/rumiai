from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class MetadataJsonError(ValueError):
    """Raised when bundled provider/model metadata JSON is not trustworthy."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MetadataJsonError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def loads_strict_metadata_json(text: str, *, source: str = "<json>") -> Any:
    try:
        return json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except MetadataJsonError as exc:
        raise MetadataJsonError(f"{source}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise MetadataJsonError(
            f"{source}: invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc


def load_strict_metadata_json(path: Path | str) -> Any:
    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise MetadataJsonError(f"{source}: {exc}") from exc
    return loads_strict_metadata_json(text, source=str(source))
