from __future__ import annotations

from blocks._common import error, ok
from domain.webhook.endpoint_store import WebhookEndpointStore


def run(input_data, context):
    del context
    data = input_data or {}
    method = str(data.get("_method") or "GET").upper()
    store = WebhookEndpointStore()
    webhook_id = str(data.get("webhook_id") or "").strip()
    if method == "GET":
        return ok({"endpoints": store.list_endpoints()})
    if method == "DELETE":
        if not webhook_id:
            return error("webhook_id is required", "INVALID_INPUT")
        return ok(store.delete(webhook_id))
    if method in {"POST", "PUT"}:
        payload = dict(data)
        payload.pop("_method", None)
        payload.pop("_headers", None)
        payload.pop("_raw_body", None)
        payload.pop("_raw_body_base64", None)
        if webhook_id:
            payload["id"] = webhook_id
        return ok(store.upsert(payload))
    return error("unsupported method", "METHOD_NOT_ALLOWED")
