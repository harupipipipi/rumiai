from __future__ import annotations

from pathlib import Path

from blocks._common import error, ok
from domain.external.io_templates import ExternalIOTemplateRegistry


def _template_catalog_items() -> list[dict]:
    try:
        from domain.templates.projectors import build_template_catalog
    except Exception:
        return []
    try:
        catalog = build_template_catalog(defaultspack_root=Path(__file__).resolve().parents[2])
    except Exception:
        return []
    items = catalog.get("external_io_templates")
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def run(input_data, context):
    del context
    data = input_data or {}
    method = str(data.get("_method") or "GET").upper()
    registry = ExternalIOTemplateRegistry(template_items=_template_catalog_items())
    if method == "GET":
        return ok(registry.catalog())
    if method == "POST":
        payload = dict(data.get("template") if isinstance(data.get("template"), dict) else data)
        payload.pop("_method", None)
        payload.pop("_headers", None)
        payload.pop("_raw_body", None)
        payload.pop("_raw_body_base64", None)
        result = registry.upsert_custom(payload)
        if not result.get("success"):
            return error(str(result.get("error") or "failed to save external template"), "EXTERNAL_TEMPLATE_SAVE_FAILED")
        return ok({key: value for key, value in result.items() if key != "error"})
    return error("unsupported method", "METHOD_NOT_ALLOWED")
