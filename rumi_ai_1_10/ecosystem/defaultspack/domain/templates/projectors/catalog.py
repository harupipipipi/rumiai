from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from ..models import ResolvedTemplate, RumiTemplate, TemplateDiagnostic, TemplatePiece
from ..registry import build_template_registry
from ..resolver import resolve_template


CATALOG_KEYS = (
    "templates",
    "field_renderers",
    "data_sources",
    "actions",
    "backend_services",
    "api_routes",
    "permissions",
    "template_diagnostics",
    "settings_sections",
    "component_bindings",
    "sidebar_items",
    "chat_renderers",
    "composer_widgets",
    "test_contracts",
)


def build_template_catalog(
    *,
    defaultspack_root: str | Path | None = None,
    roots: list[str | Path] | None = None,
) -> dict[str, Any]:
    catalog = _empty_catalog()
    registry, diagnostics = build_template_registry(
        [str(root) for root in roots] if roots is not None else None,
        defaultspack_root=str(defaultspack_root) if defaultspack_root is not None else None,
    )
    resolved_templates: list[ResolvedTemplate] = []
    for template in registry.list():
        resolved = resolve_template(template.id, registry)
        resolved_templates.append(resolved)
        diagnostics.extend(resolved.diagnostics)

    catalog = project_resolved_templates(resolved_templates)
    catalog["template_diagnostics"] = _dedupe_diagnostics(
        [*catalog["template_diagnostics"], *(_diagnostic_to_dict(item) for item in diagnostics)]
    )
    return catalog


def project_resolved_templates(resolved_templates: list[ResolvedTemplate]) -> dict[str, Any]:
    catalog = _empty_catalog()
    for resolved in resolved_templates:
        template = resolved.template
        if template is None:
            catalog["template_diagnostics"].extend(_diagnostic_to_dict(item) for item in resolved.diagnostics)
            continue

        template_diagnostics = [_diagnostic_to_dict(item) for item in resolved.diagnostics]
        catalog["templates"].append(_template_summary(template, resolved, template_diagnostics))
        catalog["template_diagnostics"].extend(template_diagnostics)

        if any(item.get("severity") == "error" for item in template_diagnostics):
            continue

        for piece in template.pieces:
            _project_piece(catalog, template, piece)

    catalog["component_bindings"].extend(_field_renderer_component_bindings(catalog["field_renderers"]))
    for key in (
        "templates",
        "field_renderers",
        "data_sources",
        "actions",
        "backend_services",
        "api_routes",
        "permissions",
        "component_bindings",
        "sidebar_items",
        "chat_renderers",
        "composer_widgets",
        "test_contracts",
    ):
        catalog[key] = _dedupe_by_id(catalog[key])
    catalog["settings_sections"] = _merge_settings_sections(catalog["settings_sections"])
    catalog["template_diagnostics"] = _dedupe_diagnostics(catalog["template_diagnostics"])
    return catalog


def _field_renderer_component_bindings(field_renderers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_part: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for renderer in field_renderers:
        part_id = str(renderer.get("part_id") or "settings").strip() or "settings"
        if part_id not in by_part:
            by_part[part_id] = {
                "id": f"template_field_renderers:{part_id}",
                "part_id": part_id,
                "component": "SettingsFieldRendererHost",
                "renderer": "template_field_renderer",
                "field_types": [],
                "renderers": [],
                "origin": {"kind": "template_catalog", "path": "domain/templates/projectors/catalog.py"},
                "_source": "template_catalog",
            }
            order.append(part_id)
        binding = by_part[part_id]
        binding["renderers"].append(deepcopy(renderer))
        binding["field_types"] = sorted(
            {
                *binding.get("field_types", []),
                *(str(value) for value in renderer.get("field_types", []) if str(value or "").strip()),
            }
        )
    return [by_part[part_id] for part_id in order]


def _project_piece(catalog: dict[str, Any], template: RumiTemplate, piece: TemplatePiece) -> None:
    kind = _value(piece.kind)
    role = str(piece.data.get("role") or piece.data.get("template_piece_type") or "").strip()

    if kind == "settings_section":
        catalog["settings_sections"].append(_settings_section(template, piece))
    elif kind == "settings_field":
        catalog["settings_sections"].append(_settings_section_for_field(template, piece))
    elif kind == "field_renderer":
        renderer = _field_renderer(template, piece)
        catalog["field_renderers"].append(renderer)
    elif kind == "frontend_component":
        catalog["component_bindings"].append(_component_binding(template, piece))
    elif kind == "sidebar_item":
        catalog["sidebar_items"].append(_metadata_item(template, piece, default_id=piece.id))
    elif kind == "chat_renderer":
        catalog["chat_renderers"].append(_metadata_item(template, piece, default_id=piece.id))
    elif kind == "composer_widget":
        catalog["composer_widgets"].append(_metadata_item(template, piece, default_id=piece.id))
    elif kind == "backend_service":
        catalog["backend_services"].append(_metadata_item(template, piece, default_id=piece.id))
    elif kind == "api_route":
        catalog["api_routes"].append(_api_route(template, piece))
    elif kind == "permission":
        catalog["permissions"].append(_permission(template, piece))
    elif kind == "test_contract":
        catalog["test_contracts"].append(_metadata_item(template, piece, default_id=piece.id))

    if role == "action" or (kind == "function" and _has_any(piece.data, ("action", "action_id", "command_id"))):
        catalog["actions"].append(_metadata_item(template, piece, default_id=piece.id))
    if role == "data_source" or (kind == "function" and _has_any(piece.data, ("data_source", "source", "query"))):
        catalog["data_sources"].append(_metadata_item(template, piece, default_id=piece.id))


def _field_renderer(template: RumiTemplate, piece: TemplatePiece) -> dict[str, Any]:
    item = _metadata_item(template, piece, default_id=piece.id)
    item.setdefault("renderer", piece.data.get("renderer") or piece.id)
    item.setdefault("component", piece.data.get("component") or "SettingsFieldRendererHost")
    item.setdefault("part_id", piece.data.get("part_id") or "settings")
    field_types = piece.data.get("field_types")
    if not isinstance(field_types, list):
        field_type = piece.data.get("field_type") or piece.data.get("type")
        field_types = [field_type] if field_type else []
    item["field_types"] = [str(value) for value in field_types if str(value or "").strip()]
    return item


def _component_binding(template: RumiTemplate, piece: TemplatePiece) -> dict[str, Any]:
    item = _metadata_item(template, piece, default_id=piece.id)
    item.setdefault("part_id", piece.data.get("part_id") or piece.data.get("part") or piece.id)
    item.setdefault("component", piece.data.get("component") or piece.data.get("renderer") or piece.id)
    item.setdefault("renderer", piece.data.get("renderer") or item.get("component"))
    if "field_types" in piece.data and isinstance(piece.data["field_types"], list):
        item["field_types"] = [str(value) for value in piece.data["field_types"] if str(value or "").strip()]
    return item


def _settings_section(template: RumiTemplate, piece: TemplatePiece) -> dict[str, Any]:
    section = piece.data.get("section") if isinstance(piece.data.get("section"), dict) else piece.data
    item = deepcopy(section) if isinstance(section, dict) else {}
    item.setdefault("id", piece.data.get("section_id") or piece.id)
    item.setdefault("label", _titleize(str(item["id"])))
    item.setdefault("fields", [])
    item.setdefault("template_id", template.id)
    item.setdefault("origin", _origin(template, piece))
    item["_source"] = _source(template)
    return item


def _settings_section_for_field(template: RumiTemplate, piece: TemplatePiece) -> dict[str, Any]:
    section_id = str(piece.data.get("section_id") or piece.data.get("section") or piece.slot or "templates").strip()
    field = piece.data.get("field") if isinstance(piece.data.get("field"), dict) else piece.data
    item = deepcopy(field) if isinstance(field, dict) else {}
    item.setdefault("id", piece.data.get("field_id") or piece.id)
    item.setdefault("label", _titleize(str(item["id"])))
    item.setdefault("type", piece.data.get("field_type") or piece.data.get("type") or "text")
    item.setdefault("renderer", piece.data.get("renderer") or item.get("type"))
    item.setdefault("component", piece.data.get("component") or "SettingsFieldRendererHost")
    item.setdefault("part_id", piece.data.get("part_id") or "settings")
    item.setdefault("template_id", template.id)
    item.setdefault("origin", _origin(template, piece))
    item["_source"] = _source(template)
    return {
        "id": section_id,
        "label": _titleize(section_id),
        "fields": [item],
        "template_id": template.id,
        "origin": _origin(template, piece),
        "_source": _source(template),
    }


def _permission(template: RumiTemplate, piece: TemplatePiece) -> dict[str, Any]:
    item = _metadata_item(template, piece, default_id=piece.id)
    item.setdefault("permission_id", piece.data.get("permission_id") or piece.id)
    item.setdefault("scope", piece.data.get("scope") or "template")
    return item


def _api_route(template: RumiTemplate, piece: TemplatePiece) -> dict[str, Any]:
    item = _metadata_item(template, piece, default_id=piece.id)
    item.setdefault("method", piece.data.get("method") or "GET")
    item.setdefault("path", piece.data.get("route_path") or piece.data.get("pattern") or piece.id)
    return item


def _metadata_item(template: RumiTemplate, piece: TemplatePiece, *, default_id: str) -> dict[str, Any]:
    item = deepcopy(piece.data)
    item.setdefault("id", item.get("name") or default_id)
    item.setdefault("kind", _value(piece.kind))
    if piece.slot is not None:
        item.setdefault("slot", piece.slot)
    if piece.order is not None:
        item.setdefault("order", piece.order)
    if piece.entrypoint is not None:
        item.setdefault("entrypoint", piece.entrypoint)
    if piece.path is not None:
        item.setdefault("path", piece.path)
    if piece.handler is not None:
        item.setdefault("handler", piece.handler)
    item.setdefault("template_id", template.id)
    item.setdefault("piece_id", piece.id)
    item.setdefault("origin", _origin(template, piece))
    item["_source"] = _source(template)
    return item


def _template_summary(
    template: RumiTemplate,
    resolved: ResolvedTemplate,
    diagnostics: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "id": template.id,
        "kind": _value(template.kind),
        "version": template.version,
        "status": _value(template.status),
        "trust_level": _value(template.trust_level),
        "extends": template.extends,
        "dependencies": list(template.dependencies),
        "capabilities": template.capabilities.to_dict(),
        "metadata": deepcopy(template.metadata),
        "source_path": _source(template),
        "ancestry": list(resolved.ancestry),
        "piece_count": len(template.pieces),
        "diagnostic_count": len(diagnostics),
        "projectable": not any(item.get("severity") == "error" for item in diagnostics),
    }


def _merge_settings_sections(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for section in sections:
        section_id = str(section.get("id") or "").strip()
        if not section_id:
            continue
        if section_id not in merged:
            merged[section_id] = deepcopy(section)
            order.append(section_id)
            merged[section_id]["fields"] = _dedupe_by_id(
                [field for field in merged[section_id].get("fields", []) if isinstance(field, dict)]
            )
            continue
        current = merged[section_id]
        for key, value in section.items():
            if key == "fields":
                continue
            if value not in (None, "", [], {}):
                current[key] = deepcopy(value)
        fields = [*current.get("fields", []), *(field for field in section.get("fields", []) if isinstance(field, dict))]
        current["fields"] = _dedupe_by_id(fields)
    return [merged[section_id] for section_id in order]


def _dedupe_by_id(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for item in items:
        item_id = str(item.get("id") or item.get("permission_id") or item.get("path") or "").strip()
        if not item_id:
            item_id = f"__index_{len(order)}"
        if item_id not in deduped:
            order.append(item_id)
        deduped[item_id] = item
    return [deduped[item_id] for item_id in order]


def _dedupe_diagnostics(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    order: list[tuple[str, str, str, str]] = []
    for item in items:
        key = (
            str(item.get("code") or ""),
            str(item.get("template_id") or ""),
            str(item.get("piece_id") or ""),
            str(item.get("source_path") or item.get("source") or ""),
        )
        if key not in deduped:
            order.append(key)
        deduped[key] = item
    return [deduped[key] for key in order]


def _diagnostic_to_dict(diagnostic: TemplateDiagnostic) -> dict[str, Any]:
    return {
        "level": diagnostic.severity,
        "severity": diagnostic.severity,
        "code": diagnostic.code,
        "message": diagnostic.message,
        "template_id": diagnostic.template_id,
        "piece_id": diagnostic.piece_id,
        "path": diagnostic.path,
        "source_path": diagnostic.source_path,
        "source": diagnostic.source_path or "template_catalog",
    }


def _empty_catalog() -> dict[str, Any]:
    return {key: [] for key in CATALOG_KEYS}


def _origin(template: RumiTemplate, piece: TemplatePiece) -> dict[str, str]:
    return {
        "kind": "template",
        "template_id": template.id,
        "piece_id": piece.id,
        "path": _source(template),
    }


def _source(template: RumiTemplate) -> str:
    return str(template.source_path) if template.source_path else ""


def _value(value: object) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _has_any(data: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return any(key in data for key in keys)


def _titleize(value: str) -> str:
    return value.replace("_", " ").replace(".", " ").strip().title() or "Template"
