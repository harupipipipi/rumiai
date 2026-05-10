from __future__ import annotations

from blocks._common import error, ok
from domain.webhook.inbound import handle_inbound_webhook


def run(input_data, context):
    webhook_id = str((input_data or {}).get("webhook_id") or "").strip()
    if not webhook_id:
        return error("webhook_id is required", "INVALID_INPUT")
    result = handle_inbound_webhook(webhook_id, input_data or {}, context or {})
    if result.get("status") == "error":
        return {**error(str(result.get("error") or "webhook failed"), str(result.get("code") or "WEBHOOK_FAILED")), "_http_status": result.get("_http_status", 400)}
    return ok(result)
