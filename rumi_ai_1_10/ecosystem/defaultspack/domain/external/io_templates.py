from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ExternalIOTemplate:
    id: str
    direction: str
    provider: str
    display_name: str
    spec: dict[str, Any]
    origin: str = "builtin"
    path: str = ""

    def as_dict(self) -> dict[str, Any]:
        payload = dict(self.spec)
        payload.update(
            {
                "id": self.id,
                "direction": self.direction,
                "provider": self.provider,
                "display_name": self.display_name,
                "origin": self.origin,
            }
        )
        if self.path:
            payload["path"] = self.path
        return payload

    @classmethod
    def from_dict(cls, spec: dict[str, Any], *, origin: str = "builtin", path: str = "") -> "ExternalIOTemplate":
        return cls(
            id=str(spec.get("id") or ""),
            direction=str(spec.get("direction") or "").strip().lower(),
            provider=str(spec.get("provider") or "").strip().lower(),
            display_name=str(spec.get("display_name") or spec.get("id") or ""),
            spec=dict(spec),
            origin=origin,
            path=path,
        )


class ExternalIOTemplateRegistry:
    def __init__(self, pack_root: Path | None = None) -> None:
        self.pack_root = pack_root or Path(__file__).resolve().parents[2]

    def list_templates(self, *, direction: str | None = None) -> list[ExternalIOTemplate]:
        wanted = str(direction or "").strip().lower()
        templates: list[ExternalIOTemplate] = []
        for directory, origin in self._template_dirs():
            for path in sorted(directory.glob("*.template.yaml")):
                template = self._load(path, origin=origin)
                if template is None:
                    continue
                if wanted and template.direction != wanted:
                    continue
                templates.append(template)
        deduped: dict[str, ExternalIOTemplate] = {}
        for template in templates:
            deduped[template.id] = template
        return sorted(deduped.values(), key=self._sort_key)

    def catalog(self) -> dict[str, Any]:
        templates = [template.as_dict() for template in self.list_templates()]
        input_templates = [item for item in templates if item.get("direction") == "input"]
        output_templates = [item for item in templates if item.get("direction") == "output"]
        custom_templates = [item for item in templates if item.get("origin") == "custom" or item.get("provider") == "custom"]
        return {
            "templates": templates,
            "input": input_templates,
            "output": output_templates,
            "custom": custom_templates,
            "extension_paths": {
                "templates": str(self.custom_templates_dir),
                "input_profiles": str(self.pack_root / "user_data" / "shared" / "input_profiles"),
                "output_profiles": str(self.pack_root / "user_data" / "shared" / "output_profiles"),
            },
        }

    def upsert_custom(self, payload: dict[str, Any]) -> dict[str, Any]:
        template = ExternalIOTemplate.from_dict(payload, origin="custom")
        validation_error = self._validate(template)
        if validation_error:
            return {"success": False, "error": validation_error}
        path = self.custom_templates_dir / (_safe_filename(template.id) + ".template.yaml")
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(template.spec)
        payload["id"] = template.id
        payload["direction"] = template.direction
        payload["provider"] = template.provider
        payload["display_name"] = template.display_name
        path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
        return {"success": True, "template": self._load(path, origin="custom").as_dict(), "path": str(path)}

    @property
    def custom_templates_dir(self) -> Path:
        return self.pack_root / "user_data" / "shared" / "external_io_templates"

    def _template_dirs(self) -> list[tuple[Path, str]]:
        return [
            (self.pack_root / "external_io_templates", "builtin"),
            (self.custom_templates_dir, "custom"),
        ]

    @staticmethod
    def _load(path: Path, *, origin: str) -> ExternalIOTemplate | None:
        try:
            data: Any = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            return None
        if not isinstance(data, dict):
            return None
        template = ExternalIOTemplate.from_dict(data, origin=origin, path=str(path))
        return template if ExternalIOTemplateRegistry._validate(template) == "" else None

    @staticmethod
    def _validate(template: ExternalIOTemplate) -> str:
        if not template.id:
            return "id is required"
        if template.direction not in {"input", "output"}:
            return "direction must be input or output"
        if not template.provider:
            return "provider is required"
        return ""

    @staticmethod
    def _sort_key(template: ExternalIOTemplate) -> tuple[int, int, str, str]:
        origin_rank = 1 if template.origin == "custom" or template.provider == "custom" else 0
        direction_rank = 0 if template.direction == "input" else 1
        provider_rank = {"line": 0, "discord": 1, "slack": 2, "generic": 3, "web": 4, "custom": 99}.get(template.provider, 50)
        return (origin_rank, direction_rank, provider_rank, template.id)


def external_io_template_catalog(pack_root: Path | None = None) -> dict[str, Any]:
    return ExternalIOTemplateRegistry(pack_root).catalog()


def _safe_filename(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", str(value or "").strip()).strip(".-")
    return slug or "external-template"
