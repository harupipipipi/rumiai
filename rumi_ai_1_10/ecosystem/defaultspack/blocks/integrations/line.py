from __future__ import annotations

import base64
import hashlib
import hmac
from typing import Any, Dict

from blocks._common import ok, error
from blocks.integrations.common import allow_unsigned_webhook_dev, headers_from_request, raw_body_bytes, text_limit
from domain.external.adapters.line import LineResponseAdapter
from domain.external.normalizer import normalize_line_event
from domain.external.pipeline import dispatch_external_event
from domain.external.response import RumiResponse
from domain.external.response_planner import ResponsePlanner
from domain.integrations.http_client import post_json
from domain.integrations.secrets import get_integration_secret, load_integration_secrets_into_env


def run(input_data, context):
    load_integration_secrets_into_env()
    headers = headers_from_request(input_data)
    raw_body = raw_body_bytes(input_data)
    verification = _verify_line(headers, raw_body)
    if not verification["ok"]:
        return {**error(verification["reason"], "SIGNATURE_INVALID"), "_http_status": 401}

    events = input_data.get("events") if isinstance(input_data.get("events"), list) else []
    results = []
    for event in events:
        if not isinstance(event, dict):
            continue
        result = _handle_event(event, context, model=str(input_data.get("model") or "") or None, verified=bool(verification["verified"]))
        results.append(result)
    return ok({"verified": verification["verified"], "events": results})


def _handle_event(
    event: Dict[str, Any],
    context,
    *,
    model: str | None = None,
    verified: bool = False,
) -> Dict[str, Any]:
    if event.get("type") != "message":
        return {"ignored": True, "reason": "unsupported LINE event", "event_type": event.get("type")}
    external_event = normalize_line_event(event, verified=verified, destination=str(event.get("destination") or ""))
    if model:
        external_event.metadata["model"] = model
    result = dispatch_external_event(
        external_event,
        input_profile_id="line.default",
        audience_policy={"default": "allow"},
        context=context,
    )
    plan = ResponsePlanner("line").plan(RumiResponse.from_result(result))
    reply = LineResponseAdapter().send(plan, event=external_event)
    return {**result, "reply": reply}


def _verify_line(headers: Dict[str, str], raw_body: bytes) -> Dict[str, Any]:
    secret = get_integration_secret("line", "LINE_CHANNEL_SECRET")
    if not secret:
        if allow_unsigned_webhook_dev():
            return {"ok": True, "verified": False, "reason": "unsigned dev mode enabled"}
        return {"ok": False, "verified": False, "reason": "LINE channel secret not configured"}
    signature = headers.get("x-line-signature", "")
    if not signature:
        return {"ok": False, "verified": False, "reason": "missing LINE signature header"}
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("ascii")
    if not hmac.compare_digest(expected, signature):
        return {"ok": False, "verified": False, "reason": "LINE signature mismatch"}
    return {"ok": True, "verified": True, "reason": ""}


def _send_line_reply(reply_token: str, text: str) -> Dict[str, Any]:
    return LineResponseAdapter().send_text_reply(reply_token, text_limit(text, 5000))
