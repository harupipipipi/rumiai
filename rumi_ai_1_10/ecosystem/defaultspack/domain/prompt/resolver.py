from __future__ import annotations

from typing import Any, Dict, Optional

from ..capability.catalog import CapabilityCatalog
from ..extensions.runtime import get_extension_registry, get_extensions_root
from .component_prompts import component_prompt_manifests, component_prompt_text


class PromptResolver:
    """Manifest-driven prompt resolver (tool/provider independent)."""

    def __init__(self) -> None:
        self._registry = get_extension_registry()
        self._extensions_root = get_extensions_root()
        self._capability_catalog = CapabilityCatalog(pack_root=self._extensions_root.parent)

    def get_manifest(self, prompt_id: str) -> Optional[Dict[str, Any]]:
        return (
            self._registry.get("prompt", prompt_id)
            or component_prompt_manifests().get(prompt_id)
            or self._capability_catalog.prompt(prompt_id)
        )

    def resolve_prompt(self, prompt_id: str, *, source_pack_id: Optional[str] = None) -> tuple[Optional[str], Optional[str]]:
        extension_manifest = self._registry.get("prompt", prompt_id)
        if extension_manifest is not None:
            config = extension_manifest.get("config", {}) or {}
            template_file = str(config.get("template_file", "prompt.md"))
            prompt_dir = self._extensions_root / "prompts" / prompt_id
            path = prompt_dir / template_file
            if path.is_file():
                actual_source_pack_id = str(
                    extension_manifest.get("source_pack_id")
                    or extension_manifest.get("_source_pack_id")
                    or self._extensions_root.parent.name
                ).strip() or None
                return path.read_text(encoding="utf-8"), actual_source_pack_id
        component = component_prompt_text(prompt_id)
        if component is not None:
            return component, self._extensions_root.parent.name
        pack_prompt = self._capability_catalog.prompt(prompt_id, source_pack_id=source_pack_id)
        if pack_prompt is not None:
            actual_source_pack_id = str(pack_prompt.get("source_pack_id") or source_pack_id or "").strip() or None
            text = self._capability_catalog.prompt_text(prompt_id, source_pack_id=actual_source_pack_id)
            if text is not None:
                return text, actual_source_pack_id
        return None, None

    def resolve_prompt_text(self, prompt_id: str, *, source_pack_id: Optional[str] = None) -> Optional[str]:
        content, _ = self.resolve_prompt(prompt_id, source_pack_id=source_pack_id)
        return content

    def render(
        self,
        prompt_id: str,
        variables: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        template = self.resolve_prompt_text(prompt_id)
        if template is None:
            return None
        values = dict(variables or {})
        rendered = template
        for key, value in values.items():
            rendered = rendered.replace("{{" + str(key) + "}}", str(value))
            rendered = rendered.replace("{{ " + str(key) + " }}", str(value))
        return rendered
