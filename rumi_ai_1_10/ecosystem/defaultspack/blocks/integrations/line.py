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
    runtime_context = _apply_endpoint_response_context(runtime_context, endpoint)
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


def _apply_endpoint_response_context(runtime_context: dict[str, Any], endpoint: WebhookEndpoint) -> dict[str, Any]:
    updated = dict(runtime_context or {})
    response = endpoint.response if isinstance(endpoint.response, dict) else {}
    if not response:
        return updated

    mode = str(response.get("mode") or "").strip().lower()
    prompt_prefix = str(
        response.get("prompt_prefix")
        or response.get("instruction_prefix")
        or response.get("computer_use_prompt")
        or _line_biz_prompt_prefix(response, mode=mode)
        or ""
    ).strip()
    if prompt_prefix:
        updated.setdefault("external_prompt_prefix", prompt_prefix)

    prompt_suffix = str(
        response.get("prompt_suffix")
        or response.get("instruction_suffix")
        or ""
    ).strip()
    if prompt_suffix:
        updated.setdefault("external_prompt_suffix", prompt_suffix)

    target_app = str(
        response.get("target_app")
        or response.get("computer_use_target_app")
        or ("Google Chrome" if mode == "computer_use_line_biz" else "")
        or ""
    ).strip()
    if target_app:
        updated.setdefault("computer_use_target_app", target_app)

    target_title = str(
        response.get("target_title")
        or response.get("computer_use_target_title")
        or ("LINE" if mode == "computer_use_line_biz" else "")
        or ""
    ).strip()
    if target_title:
        updated.setdefault("computer_use_target_title", target_title)

    tool_policy = dict(updated.get("profile_policy") if isinstance(updated.get("profile_policy"), dict) else {})
    response_tool_policy = response.get("tool_policy") if isinstance(response.get("tool_policy"), dict) else {}
    if response_tool_policy:
        tool_policy.update(response_tool_policy)
    if _truthy(
        response.get("auto_approve")
        or response.get("auto_approve_computer_use")
        or response.get("yolo_mode")
    ):
        tool_policy["yolo_mode"] = True
    if tool_policy:
        updated["profile_policy"] = tool_policy

    if _truthy(response.get("user_requested_computer_use")) or target_app or target_title or prompt_prefix:
        updated.setdefault("user_requested_computer_use", True)

    if _suppress_provider_reply(response):
        updated.setdefault(
            "response_prompt_decision",
            {
                "action": "store_only",
                "reason": "provider reply suppressed by LINE endpoint response settings",
                "sensitivity": "local_only",
                "metadata": {
                    "source": "line_endpoint_response",
                    "mode": str(response.get("mode") or ""),
                },
            },
        )

    return updated


def _line_biz_prompt_prefix(response: dict[str, Any], *, mode: str = "") -> str:
    resolved_mode = (mode or str(response.get("mode") or "")).strip().lower()
    if resolved_mode != "computer_use_line_biz":
        return ""
    chat_url = str(
        response.get("line_biz_chat_url")
        or response.get("chat_url")
        or response.get("computer_use_target_url")
        or ""
    ).strip()
    if not chat_url:
        return ""
    reply_language = str(
        response.get("line_biz_reply_language")
        or response.get("reply_language")
        or "Japanese"
    ).strip()
    return (
        "Use computer_use in Google Chrome to open "
        f"{chat_url} and reply in {reply_language} inside LINE Official Account Manager. "
        "Start by checking computer.windows, and if a visible Google Chrome LINE window exists, "
        "target it with computer.select_window before screenshots or clicks. "
        "This Windows workflow only works against a visible desktop Chrome window, so if Chrome is "
        "not visible return a short local note asking for the LINE Biz window to be opened on screen. "
        "Read the latest visible customer message in that chat, answer it clearly, "
        "send the message in LINE Biz, and only after the send succeeds return a short local confirmation."
    )


def _suppress_provider_reply(response: dict[str, Any]) -> bool:
    if _truthy(response.get("suppress_provider_reply")):
        return True
    mode = str(response.get("mode") or "").strip().lower()
    return mode in {
        "store_only",
        "local_only",
        "web_local",
        "tool_only",
        "computer_use_line_biz",
        "computer_use_only",
    }


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)
