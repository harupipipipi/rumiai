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
        is_custom = self.origin == "custom" or self.provider == "custom"
        payload.update(
            {
                "id": self.id,
                "direction": self.direction,
                "provider": self.provider,
                "display_name": self.display_name,
                "origin": self.origin,
                "setup_mode": "custom" if is_custom else "copy_paste_select",
            }
        )
        if not is_custom:
            payload["copy_paste_setup"] = _copy_paste_setup(payload)
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
    def __init__(self, pack_root: Path | None = None, template_items: list[dict[str, Any]] | None = None) -> None:
        self.pack_root = pack_root or Path(__file__).resolve().parents[2]
        self.template_items = [item for item in (template_items or []) if isinstance(item, dict)]

    def list_templates(self, *, direction: str | None = None) -> list[ExternalIOTemplate]:
        wanted = str(direction or "").strip().lower()
        templates: list[ExternalIOTemplate] = []
        templates.extend(self._load_yaml_templates(self.pack_root / "external_io_templates", origin="builtin"))
        templates.extend(self._template_item_templates())
        templates.extend(self._load_yaml_templates(self.custom_templates_dir, origin="custom"))
        deduped: dict[str, ExternalIOTemplate] = {}
        for template in templates:
            deduped[template.id] = template
        values = [template for template in deduped.values() if not wanted or template.direction == wanted]
        return sorted(values, key=self._sort_key)

    def catalog(self) -> dict[str, Any]:
        templates = [template.as_dict() for template in self.list_templates()]
        input_templates = [item for item in templates if item.get("direction") == "input"]
        output_templates = [item for item in templates if item.get("direction") == "output"]
        custom_templates = [item for item in templates if item.get("origin") == "custom" or item.get("provider") == "custom"]
        builtin_input = [item for item in input_templates if item.get("provider") != "custom" and item.get("origin") != "custom"]
        builtin_output = [item for item in output_templates if item.get("provider") != "custom" and item.get("origin") != "custom"]
        return {
            "templates": templates,
            "input": input_templates,
            "output": output_templates,
            "builtin_input": builtin_input,
            "builtin_output": builtin_output,
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

    def _load_yaml_templates(self, directory: Path, *, origin: str) -> list[ExternalIOTemplate]:
        templates: list[ExternalIOTemplate] = []
        for path in sorted(directory.glob("*.template.yaml")):
            template = self._load(path, origin=origin)
            if template is not None:
                templates.append(template)
        return templates

    def _template_item_templates(self) -> list[ExternalIOTemplate]:
        templates: list[ExternalIOTemplate] = []
        for item in self.template_items:
            template = ExternalIOTemplate.from_dict(
                item,
                origin="template",
                path=str(item.get("_source") or item.get("path") or ""),
            )
            if self._validate(template) == "":
                templates.append(template)
        return templates

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


def external_io_template_catalog(
    pack_root: Path | None = None,
    *,
    template_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return ExternalIOTemplateRegistry(pack_root, template_items=template_items).catalog()


def _safe_filename(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", str(value or "").strip()).strip(".-")
    return slug or "external-template"


def _copy_paste_setup(spec: dict[str, Any]) -> dict[str, Any]:
    endpoint = spec.get("endpoint") if isinstance(spec.get("endpoint"), dict) else {}
    routes: list[str] = []
    route = endpoint.get("route") if isinstance(endpoint, dict) else None
    if route:
        routes.append(str(route))
    endpoint_routes = endpoint.get("routes") if isinstance(endpoint, dict) else None
    if isinstance(endpoint_routes, list):
        routes.extend(str(item) for item in endpoint_routes if str(item or "").strip())
    fields = spec.get("fields") if isinstance(spec.get("fields"), list) else []
    tokens = spec.get("tokens") if isinstance(spec.get("tokens"), list) else []
    setup = {
        "mode": "copy_paste_select",
        "endpoint_id": str(endpoint.get("id") or "") if isinstance(endpoint, dict) else "",
        "routes": routes,
        "input_profile_id": str(spec.get("input_profile_id") or ""),
        "output_profile_id": str(spec.get("output_profile_id") or ""),
        "tokens": [
            {
                "provider": str(spec.get("provider") or ""),
                "kind": str(token.get("kind") or ""),
                "label": str(token.get("label") or token.get("kind") or ""),
                "paste": True,
            }
            for token in tokens
            if isinstance(token, dict)
        ],
        "fields": [
            {
                "id": str(field.get("id") or ""),
                "label": str(field.get("label") or field.get("id") or ""),
                "secret": bool(field.get("secret")),
                "paste": True,
            }
            for field in fields
            if isinstance(field, dict)
        ],
    }
    if spec.get("direction") == "input" and routes:
        setup["public_url"] = {
            "provider": "cloudflare_quick_tunnel",
            "route_path": routes[0],
            "copy_to_provider_webhook_url": True,
        }
    if spec.get("setup_steps"):
        setup["setup_steps"] = spec.get("setup_steps")
    return setup
