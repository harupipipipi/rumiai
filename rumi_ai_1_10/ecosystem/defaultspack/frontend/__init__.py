"""frontend module - Web UI management."""
from __future__ import annotations
from typing import Any, Dict, List
class FrontendManager:
    def __init__(self):
        self._components = {}; self._layout_config = {}; self._settings_injections = []
    def register_component(self, name: str, config: Dict[str, Any]): self._components[name] = config
    def list_components(self) -> List[str]: return list(self._components.keys())
    def get_layout(self) -> Dict[str, Any]: return dict(self._layout_config)
    def save_layout(self, config: Dict[str, Any]): self._layout_config = config
    def inject_settings(self, category: str, html: str):
        self._settings_injections.append({"category": category, "html": html})
    def get_settings_injections(self) -> List[Dict[str, Any]]: return list(self._settings_injections)
