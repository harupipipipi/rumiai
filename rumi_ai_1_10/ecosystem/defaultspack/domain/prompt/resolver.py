from __future__ import annotations

from typing import Any, Dict, Optional

from ..extensions.runtime import get_extension_registry, get_extensions_root


class PromptResolver:
    """Manifest-driven prompt resolver (tool/provider independent)."""

    def __init__(self) -> None:
        self._registry = get_extension_registry()
        self._extensions_root = get_extensions_root()

    def get_manifest(self, prompt_id: str) -> Optional[Dict[str, Any]]:
        return self._registry.get("prompt", prompt_id)

    def resolve_prompt_text(self, prompt_id: str) -> Optional[str]:
        manifest = self.get_manifest(prompt_id)
        if manifest is None:
            return None
        config = manifest.get("config", {}) or {}
        template_file = str(config.get("template_file", "prompt.md"))
        prompt_dir = self._extensions_root / "prompts" / prompt_id
        path = prompt_dir / template_file
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8")

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
