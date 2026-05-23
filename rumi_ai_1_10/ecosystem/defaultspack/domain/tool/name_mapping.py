from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ToolNameMapping:
    forward: dict[str, str] = field(default_factory=dict)
    reverse: dict[str, str] = field(default_factory=dict)

    def alias_for(self, name: str) -> str:
        return self.forward.get(name, name)

    def original_for(self, alias: str) -> str:
        return self.reverse.get(alias, alias)

    def to_dict(self) -> dict[str, dict[str, str]]:
        return {"forward": dict(self.forward), "reverse": dict(self.reverse)}


def sanitize_tool_name(name: str, *, regex: str = r"^[A-Za-z_][A-Za-z0-9_.:-]{0,127}$", max_length: int = 128, used: set[str] | None = None) -> str:
    text = str(name or "").strip()
    if text and re.fullmatch(regex, text) and len(text) <= max_length:
        candidate = text
    else:
        candidate = re.sub(r"[^A-Za-z0-9_.:-]+", "_", text).strip("_")
        if not candidate:
            candidate = "tool"
        if not re.match(r"^[A-Za-z_]", candidate):
            candidate = "_" + candidate
        candidate = candidate[:max_length] or "_tool"
    registry = used if used is not None else set()
    if candidate not in registry:
        registry.add(candidate)
        return candidate
    base = candidate[: max(1, max_length - 8)]
    suffix = 2
    while True:
        deduped = f"{base}_{suffix}"[:max_length]
        if deduped not in registry:
            registry.add(deduped)
            return deduped
        suffix += 1


def build_tool_name_mapping(names: list[str], quirks: dict | None = None) -> ToolNameMapping:
    quirks = quirks if isinstance(quirks, dict) else {}
    regex = str(quirks.get("tool_name_regex") or r"^[A-Za-z_][A-Za-z0-9_.:-]{0,127}$")
    max_length = int(quirks.get("tool_name_max_length") or 128)
    used: set[str] = set()
    mapping = ToolNameMapping()
    for name in names:
        original = str(name or "").strip()
        if not original:
            continue
        alias = sanitize_tool_name(original, regex=regex, max_length=max_length, used=used)
        mapping.forward[original] = alias
        mapping.reverse[alias] = original
    return mapping
