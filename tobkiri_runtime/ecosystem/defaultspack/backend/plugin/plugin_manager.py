"""Plugin bundle compatibility layer."""

from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class PluginManifest:
    plugin_id: str = ""
    plugin_uuid: str = ""
    version: str = "0.1.0"
    display_name: str = ""
    description: str = ""
    dependencies: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    prompts: List[str] = field(default_factory=list)
    ai_clients: List[str] = field(default_factory=list)
    supporters: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.plugin_uuid:
            self.plugin_uuid = str(
                uuid.uuid5(uuid.NAMESPACE_DNS, f"plugin:{self.plugin_id}:{self.version}")
            )

    @property
    def uuid(self) -> str:
        return self.plugin_uuid

    @uuid.setter
    def uuid(self, value: str) -> None:
        self.plugin_uuid = value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "uuid": self.plugin_uuid,
            "plugin_uuid": self.plugin_uuid,
            "version": self.version,
            "display_name": self.display_name,
            "description": self.description,
            "dependencies": self.dependencies,
            "tools": self.tools,
            "prompts": self.prompts,
            "ai_clients": self.ai_clients,
            "supporters": self.supporters,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PluginManifest":
        data = dict(data)
        if "uuid" in data and "plugin_uuid" not in data:
            data["plugin_uuid"] = data["uuid"]
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)


class PluginManager:
    """Install/uninstall plugins with a small in-memory index."""

    def __init__(self, plugins_dir: Optional[Path] = None) -> None:
        self._plugins: Dict[str, PluginManifest] = {}
        self._dir = plugins_dir

    def scan(self, plugins_dir: Optional[Path] = None) -> int:
        directory = plugins_dir or self._dir
        if directory is None or not directory.exists():
            return 0
        self._dir = directory
        count = 0
        for child in sorted(directory.iterdir()):
            manifest_file = child / "manifest.json"
            if not manifest_file.is_file():
                continue
            try:
                data = json.loads(manifest_file.read_text(encoding="utf-8"))
                manifest = PluginManifest.from_dict(data)
                self._plugins[manifest.plugin_id] = manifest
                count += 1
            except Exception:
                continue
        return count

    def list_plugins(self) -> List[PluginManifest]:
        return self.list_all()

    def install(self, source_dir: Path) -> Optional[PluginManifest]:
        manifest_file = source_dir / "manifest.json"
        if not manifest_file.is_file():
            return None
        manifest = PluginManifest.from_dict(
            json.loads(manifest_file.read_text(encoding="utf-8"))
        )
        for dependency in manifest.dependencies:
            if dependency not in self._plugins:
                raise ValueError(f"Missing dependency: {dependency}")
        if self._dir is not None:
            target = self._dir / manifest.plugin_id
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(source_dir, target)
        self._plugins[manifest.plugin_id] = manifest
        return manifest

    def install_plugin(self, source_dir: Path) -> Optional[PluginManifest]:
        return self.install(source_dir)

    def uninstall(self, plugin_id: str) -> bool:
        if plugin_id not in self._plugins:
            return False
        for other_id, other_manifest in self._plugins.items():
            if other_id != plugin_id and plugin_id in other_manifest.dependencies:
                raise ValueError(f"Cannot uninstall: {other_id} depends on {plugin_id}")
        del self._plugins[plugin_id]
        if self._dir is not None:
            target = self._dir / plugin_id
            if target.exists():
                shutil.rmtree(target)
        return True

    def uninstall_plugin(self, plugin_id: str) -> bool:
        return self.uninstall(plugin_id)

    def get(self, plugin_id: str) -> Optional[PluginManifest]:
        return self._plugins.get(plugin_id)

    def list_all(self) -> List[PluginManifest]:
        return list(self._plugins.values())
