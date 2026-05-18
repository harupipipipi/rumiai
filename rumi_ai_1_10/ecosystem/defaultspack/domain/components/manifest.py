from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DomainComponent:
    category: str
    component_id: str
    manifest: dict[str, Any]
    manifest_path: Path
    source_pack_id: str = ""

    @property
    def id(self) -> str:
        return self.component_id

    @property
    def kind(self) -> str:
        return str(self.manifest.get("kind") or "")

    @property
    def status(self) -> str:
        return str(self.manifest.get("status") or "")

    @property
    def aliases(self) -> tuple[str, ...]:
        return tuple(iter_component_aliases(self.manifest))

    def as_dict(self) -> dict[str, Any]:
        data = dict(self.manifest)
        data["source_path"] = str(self.manifest_path)
        if self.source_pack_id:
            data["source_pack_id"] = self.source_pack_id
        return data


def iter_component_aliases(manifest: dict[str, Any]) -> tuple[str, ...]:
    aliases: list[str] = []

    def add(value: Any) -> None:
        if isinstance(value, str):
            item = value.strip()
            if item and item not in aliases:
                aliases.append(item)
        elif isinstance(value, (list, tuple, set)):
            for nested in value:
                add(nested)
        elif isinstance(value, dict):
            for nested in value.values():
                add(nested)

    add(manifest.get("aliases"))
    compatibility = manifest.get("compatibility")
    if isinstance(compatibility, dict):
        add(compatibility.get("aliases"))
        add(compatibility.get("legacy_ids"))
        add(compatibility.get("legacy_imports"))
    return tuple(aliases)
