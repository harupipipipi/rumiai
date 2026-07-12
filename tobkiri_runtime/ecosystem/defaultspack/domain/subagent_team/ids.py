from __future__ import annotations

import hashlib
import re
import uuid
from typing import Iterable


_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"
_SAFE_ID_RE = re.compile(r"[^a-zA-Z0-9_-]+")


def slug_id(value: str, *, fallback: str = "item", max_length: int = 48) -> str:
    clean = _SAFE_ID_RE.sub("-", str(value or "").strip()).strip("-").lower()
    clean = re.sub(r"-{2,}", "-", clean)
    if not clean:
        clean = fallback
    return clean[:max_length].strip("-") or fallback


def generate_short_id(prefix: str = "t", *, existing: Iterable[str] | None = None, length: int = 7) -> str:
    seen = {str(item) for item in (existing or [])}
    safe_prefix = slug_id(prefix, fallback="t", max_length=8).replace("-", "")
    while True:
        token = _base36(uuid.uuid4().int)[: max(4, int(length))]
        short_id = safe_prefix + "_" + token
        if short_id not in seen:
            return short_id


def generate_internal_uuid() -> str:
    """Return an opaque internal id for newly-created subagents."""
    return str(uuid.uuid4())


def is_uuid(value: str | None) -> bool:
    try:
        uuid.UUID(str(value or ""))
    except (TypeError, ValueError):
        return False
    return True


def stable_short_id(
    prefix: str,
    seed: str = "",
    *,
    existing: Iterable[str] | None = None,
    length: int = 7,
) -> str:
    safe_prefix = slug_id(prefix, fallback="t", max_length=8).replace("-", "")
    digest = hashlib.sha1(str(seed or "").encode("utf-8")).digest()
    number = int.from_bytes(digest[:8], "big")
    base = safe_prefix + "_" + _base36(number)[: max(4, int(length))]
    seen = {str(item) for item in (existing or [])}
    if base not in seen:
        return base
    counter = 2
    while True:
        candidate = f"{base}_{counter}"
        if candidate not in seen:
            return candidate
        counter += 1


def channel_id_from_name(name: str) -> str:
    return slug_id(name, fallback="team", max_length=48)


def ensure_short_id(metadata: dict | None, *, prefix: str, seed: str, existing: Iterable[str] | None = None) -> tuple[str, dict]:
    data = dict(metadata or {})
    current = str(data.get("short_id") or "").strip()
    if current:
        return current, data
    candidate = stable_short_id(prefix, seed)
    if candidate in {str(item) for item in (existing or [])}:
        candidate = generate_short_id(prefix, existing=existing)
    data["short_id"] = candidate
    return candidate, data


def _base36(value: int) -> str:
    number = abs(int(value))
    if number == 0:
        return "0"
    chars: list[str] = []
    while number:
        number, idx = divmod(number, 36)
        chars.append(_ALPHABET[idx])
    return "".join(reversed(chars))
