from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def provenance_event(source: str, detail: Mapping[str, Any] | None = None) -> dict[str, Any]:
    payload = dict(detail or {})
    return {"source": source, "detail": {str(key): payload[key] for key in sorted(payload, key=str)}}
