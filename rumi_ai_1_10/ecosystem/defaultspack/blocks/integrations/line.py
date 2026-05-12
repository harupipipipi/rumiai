from __future__ import annotations

import base64
import hashlib
import hmac
from typing import Any, Dict

from blocks._common import ok, error
from blocks.integrations.common import allow_unsigned_webhook_dev, headers_from_request, raw_body_bytes, text_limit
from domain.external.adapters.line import LineResponseAdapter
from domain.external.audience_policy_registry import AudiencePolicyRegistry
from domain.external.normalizer import normalize_line_event
from domain.external.pipeline import dispatch_external_event
from domain.external.response import RumiResponse
from domain.external.response_planner import ResponsePlanner
from domain.external.source_store import ExternalSourceStore
from domain.external.targeting import origin_from_external_event
from domain.integrations.http_client import post_json
from domain.integrations.secrets import get_integration_secret, load_integration_secrets_into_env
from domain.webhook.endpoint import WebhookEndpoint
from domain.webhook.endpoint_resolver import ProviderEndpointResolver


def run(input_data, context):
    load_integration_secrets_into_env()
    endpoint = ProviderEndpointResolver().resolve("line", input_data)
    if endpoint is None:
        return {**error("LINE webhook endpoint not found", "WEBHOOK_ENDPOINT_NOT_FOUND"), "_http_status": 404}
    if not endpoint.enabled:
        return {**error("LINE webhook endpoint disabled", "WEBHOOK_ENDPOINT_DISABLED"), "_http_status": 403}

    headers = headers_from_request(input_data)
    raw_body = raw_body_bytes(input_data)
    security = endpoint.security if isinstance(endpoint.security, dict) else {}
    verification = {"ok": True, "verified": False, "reason": "provider signature disabled"}
    if str(security.get("mode") or "provider_signature") != "none":
        verification = _verify_line(headers, raw_body)
    if not verification["ok"]:
        return {**error(verification["reason"], "SIGNATURE_INVALID"), "_http_status": 401}

    events = input_data.get("events") if isinstance(input_data.get("events"), list) else []
    results = []
    destination = str(input_data.get("destination") or "")
    model = str(input_data.get("model") or endpoint.conversation.get("model") or "") or None
    for event in events:
        if not isinstance(event, dict):
            continue
        result = _handle_event(
            event,
            context,
            model=model,
            verified=bool(verification["verified"]),
            destination=destination,
            endpoint=endpoint,
        )
        results.append(result)
    return ok({"verified": verification["verified"], "endpoint": endpoint.as_dict(), "events": results})


def _handle_event(
    event: Dict[str, Any],
    context,
    *,
    model: str | None = None,
    verified: bool = False,
    destination: str = "",
    endpoint: WebhookEndpoint,
) -> Dict[str, Any]:
    if event.get("type") != "message":
        return {"ignored": True, "reason": "unsupported LINE event", "event_type": event.get("type")}
    external_event = normalize_line_event(event, verified=verified, destination=destination)
    if model:
        external_event.metadata["model"] = model
    origin = origin_from_external_event(external_event)
    source_record = ExternalSourceStore().record_origin(origin, verified=verified)
    external_event.metadata["origin"] = origin.as_dict()
    external_event.metadata["source_record"] = source_record
    runtime_context = dict(context or {})
    runtime_context.setdefault("webhook_endpoint", endpoint.as_dict())
    runtime_context.setdefault("output_profile_id", endpoint.response_profile_id)
    runtime_context.setdefault("response_profile_id", endpoint.response_profile_id)
    runtime_context.setdefault("conversation", dict(endpoint.conversation))
    runtime_context.setdefault("source_record", source_record)
    policy = AudiencePolicyRegistry().resolve(endpoint.audience_policy_id, event=external_event)
    result = dispatch_external_event(
        external_event,
        input_profile_id=endpoint.input_profile_id,
        audience_policy=policy,
        context=runtime_context,
        send_response=True,
    )
    plan = result.get("response_plan") if isinstance(result.get("response_plan"), dict) else ResponsePlanner("line").plan(RumiResponse.from_result(result))
    reply = _send_response_plan(plan, external_event, context=runtime_context)
    return {**result, "reply": reply}


def _send_response_plan(plan: dict[str, Any], external_event, *, context: dict[str, Any] | None = None) -> Dict[str, Any]:
    action_plan = (plan.get("metadata") or {}).get("response_action_plan") if isinstance(plan.get("metadata"), dict) else {}
    if isinstance(action_plan, dict) and not action_plan.get("external_reply", True):
        return {"sent": False, "reason": "external reply suppressed by response prompt policy"}
    return LineResponseAdapter().send(plan, event=external_event, context=context)


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
