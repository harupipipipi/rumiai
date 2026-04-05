"""
plugin module - Plugin management (bundles of tool + ai_client + prompt).

Plugins are self-contained units with manifest, UUID, version,
dependencies. Supports atomic install/uninstall.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PluginManifest:
    plugin_id: str
    uuid: str = ""
    version: str = "0.0.1"
    display_name: str = ""
    description: str = ""
    author: str = ""
    dependencies: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    prompts: List[str] = field(default_factory=list)
    ai_clients: List[str] = field(default_factory=list)
    install_script: Optional[str] = None
    uninstall_script: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "uuid": self.uuid,
            "version": self.version,
            "display_name": self.display_name,
            "description": self.description,
            "dependencies": self.dependencies,
            "tools": self.tools,
            "prompts": self.prompts,
        }


class PluginManager:
    """Manages plugin lifecycle: install, uninstall, list, dependency check."""

    def __init__(self):
        self._lock = threading.RLock()
        self._plugins: Dict[str, PluginManifest] = {}

    def install(self, manifest: PluginManifest) -> Dict[str, Any]:
        with self._lock:
            # Check dependencies
            missing = [d for d in manifest.dependencies if d not in self._plugins]
            if missing:
                return {"success": False, "error": f"Missing dependencies: {missing}"}
            self._plugins[manifest.plugin_id] = manifest
            return {"success": True, "plugin_id": manifest.plugin_id}

    def uninstall(self, plugin_id: str) -> Dict[str, Any]:
        with self._lock:
            # Check if other plugins depend on this
            dependents = [
                pid for pid, p in self._plugins.items()
                if plugin_id in p.dependencies
            ]
            if dependents:
                return {"success": False, "error": f"Required by: {dependents}"}
            removed = self._plugins.pop(plugin_id, None)
            return {"success": removed is not None, "plugin_id": plugin_id}

    def get(self, plugin_id: str) -> Optional[PluginManifest]:
        return self._plugins.get(plugin_id)

    def list_all(self) -> List[PluginManifest]:
        return list(self._plugins.values())
