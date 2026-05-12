from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any, Dict

from blocks._common import ok, error
from blocks.integrations.common import allow_unsigned_webhook_dev, headers_from_request, raw_body_bytes, text_limit
from domain.external.adapters.line import LineResponseAdapter
from domain.external.audience_policy import AudiencePolicy
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
    raw_body = raw_body_bytes(input_data)
    endpoint_input = {} if _has_raw_body(input_data) else input_data
    endpoint = ProviderEndpointResolver().resolve("line", endpoint_input)
    if endpoint is None:
        return {**error("LINE webhook endpoint not found", "WEBHOOK_ENDPOINT_NOT_FOUND"), "_http_status": 404}
    if not endpoint.enabled:
        return {**error("LINE webhook endpoint disabled", "WEBHOOK_ENDPOINT_DISABLED"), "_http_status": 403}

    headers = headers_from_request(input_data)
    security = endpoint.security if isinstance(endpoint.security, dict) else {}
    verification = {"ok": True, "verified": False, "reason": "provider signature disabled"}
    if str(security.get("mode") or "provider_signature") != "none":
        verification = _verify_line(headers, raw_body)
    if not verification["ok"]:
        return {**error(verification["reason"], "SIGNATURE_INVALID"), "_http_status": 401}
    request_payload, parse_error = _payload_from_raw_body(input_data, raw_body)
    if parse_error:
        return {**error(parse_error, "INVALID_LINE_BODY"), "_http_status": 400}

    events = request_payload.get("events") if isinstance(request_payload.get("events"), list) else []
    results = []
    destination = str(request_payload.get("destination") or "")
    model = str(request_payload.get("model") or endpoint.conversation.get("model") or "") or None
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
    _apply_external_output_context(runtime_context)
    runtime_context.setdefault("webhook_endpoint", endpoint.as_dict())
    runtime_context.setdefault("output_profile_id", endpoint.response_profile_id)
    runtime_context.setdefault("response_profile_id", endpoint.response_profile_id)
    runtime_context.setdefault("conversation", dict(endpoint.conversation))
    runtime_context.setdefault("source_record", source_record)
    policy = AudiencePolicyRegistry().resolve(endpoint.audience_policy_id, event=external_event)
    decision = AudiencePolicy(policy).evaluate(external_event)
    if not decision.allowed:
        return _policy_denied_result(external_event, decision)
    result = dispatch_external_event(
        external_event,
        input_profile_id=endpoint.input_profile_id,
        audience_policy=policy,
        audience_decision=decision,
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


def _payload_from_raw_body(input_data, raw_body: bytes) -> tuple[dict[str, Any], str]:
    if not _has_raw_body(input_data):
        return (input_data if isinstance(input_data, dict) else {}), ""
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}, "invalid LINE JSON body"
    if not isinstance(payload, dict):
        return {}, "LINE JSON body must be an object"
    return payload, ""


def _has_raw_body(input_data) -> bool:
    return isinstance(input_data, dict) and ("_raw_body_base64" in input_data or "_raw_body" in input_data)


def _apply_external_output_context(runtime_context: dict[str, Any]) -> None:
    output = _frontend_external_output_settings()
    send_mode = str(output.get("output_send_mode") or output.get("send_mode") or "").strip()
    if send_mode:
        runtime_context.setdefault("send_mode", send_mode)
        runtime_context.setdefault("line_send_mode", send_mode)
    output_profile_id = str(output.get("output_profile_id") or "").strip()
    if output_profile_id:
        runtime_context.setdefault("output_profile_id", output_profile_id)
        runtime_context.setdefault("response_profile_id", output_profile_id)
    target_id = str(output.get("output_target_id") or "").strip()
    if target_id:
        runtime_context.setdefault("target_id", target_id)
        runtime_context.setdefault("line_target_id", target_id)


def _frontend_external_output_settings() -> dict[str, Any]:
    override = os.environ.get("RUMI_DEFAULTSPACK_FRONTEND_SETTINGS_PATH", "").strip()
    path = Path(override) if override else Path(__file__).resolve().parents[2] / "user_data" / "shared" / "frontend_settings.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    output = data.get("external_output") if isinstance(data.get("external_output"), dict) else {}
    return dict(output)


def _policy_denied_result(external_event, decision) -> Dict[str, Any]:
    return {
        "status": "denied",
        "assistant_text": "",
        "policy": decision.as_dict(),
        "event": external_event.as_dict(),
        "reply": {"sent": False, "reason": "audience policy denied"},
    }


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
