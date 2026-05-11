from __future__ import annotations

from blocks._common import error, ok
from domain.external.io_templates import ExternalIOTemplateRegistry


def run(input_data, context):
    del context
    data = input_data or {}
    method = str(data.get("_method") or "GET").upper()
    registry = ExternalIOTemplateRegistry()
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
