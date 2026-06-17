from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import threading
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict

from blocks._common import ok, error
from blocks.integrations.common import allow_unsigned_webhook_dev, headers_from_request, raw_body_bytes, text_limit
from domain.external.adapters.line import LineResponseAdapter
from domain.external.audience_policy import AudiencePolicy
from domain.external.audience_policy_registry import AudiencePolicyRegistry
from domain.external.chat_link import (
    CHAT_LINK_PROMPT,
    envelope_overrides as chat_link_envelope_overrides,
    handle_chat_link_message,
    linked_conversation_id as chat_linked_conversation_id,
)
from domain.external.normalizer import normalize_line_event
from domain.external.pipeline import dispatch_external_event
from domain.external.response import RumiResponse
from domain.external.response_planner import ResponsePlanner
from domain.external.source_store import ExternalSourceStore
from domain.external.targeting import origin_from_external_event
from domain.frontend.command_registry import SlashCommandRegistry
from domain.integrations.secrets import get_integration_secret, load_integration_secrets_into_env
from domain.webhook.endpoint import WebhookEndpoint
from domain.webhook.endpoint_resolver import ProviderEndpointResolver


_LOGGER = logging.getLogger(__name__)
_LINE_WEBHOOK_ACK_TEXT = "\u5c4a\u3044\u305f\u3088\uff01"
_LINE_LONG_TASK_NOTICE_TEXT = "40秒たちました。まだ処理中です。完了したらpush/postで送ります。"
_LINE_SHORT_ERROR_TEXT = "エラーが出ました。少し後で再送してね。"
_LINE_REPLY_GUIDANCE_PROMPT = (
    "LINE replyは短命・1回のみ。最終回答はreply用に短く書く。"
    "長くかかりそうなら始める前に一度許可を取る。"
    "返信しない判断なら一度だけ「replyで送れます。送りますか？」と確認。"
    "期限切れ/使用済みならpushを提案。"
)


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
    hook_settings = _frontend_hook_settings()
    model = str(request_payload.get("model") or _line_response_model(endpoint, hook_settings) or "") or None
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
            hook_settings=hook_settings,
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
    hook_settings: dict[str, Any] | None = None,
) -> Dict[str, Any]:
    if event.get("type") != "message":
        return {"ignored": True, "reason": "unsupported LINE event", "event_type": event.get("type")}
    hook_settings = dict(hook_settings or {})
    external_event = normalize_line_event(event, verified=verified, destination=destination)
    if model:
        external_event.metadata["model"] = model
    mentioned = _line_message_mentions_bot(event, destination=destination)
    require_group_mention = _require_line_group_mention(endpoint, external_event)
    external_event.metadata["line_mention"] = {
        "mentioned": mentioned,
        "require_group_mention": require_group_mention,
    }
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
    _apply_hook_context(runtime_context, hook_settings, endpoint=endpoint)
    linked_conversation_id = chat_linked_conversation_id(runtime_context)
    if linked_conversation_id:
        runtime_context.setdefault("conversation_id", linked_conversation_id)
        external_event.metadata["linked_conversation_id"] = linked_conversation_id
    policy = AudiencePolicyRegistry().resolve(endpoint.audience_policy_id, event=external_event)
    command_result = None

    # Slash commands are a safe bootstrap path in LINE groups: the source may not
    # be enabled yet, and LINE mention metadata is often absent for plain "/..."
    # messages. Keep signature/rate/message-type policy, but allow this source.
    if _line_slash_command_requested(event, hook_settings):
        command_policy = _allow_current_source(policy, external_event)
        command_decision = AudiencePolicy(command_policy).evaluate(external_event, mentioned=True)
        if not command_decision.allowed:
            return _policy_denied_result(external_event, command_decision)
        command_result = _handle_line_command(
            event,
            external_event,
            endpoint=endpoint,
            context=runtime_context,
            hook_settings=hook_settings,
            audience_decision=command_decision,
            audience_policy=command_policy,
        )
        if command_result is not None:
            return command_result

    chat_link_result = handle_chat_link_message(
        external_event,
        runtime_context,
        _line_message_text(event),
        model=model,
    )
    if chat_link_result is not None:
        reply = _send_response_plan(chat_link_result["response_plan"], external_event, context=runtime_context)
        return {**chat_link_result, "reply": reply}

    reaction = _line_reaction_decision(event, external_event, hook_settings)
    if require_group_mention:
        policy = _require_audience_mention(policy)
        policy = _allow_current_scope(policy, external_event)
    effective_mentioned = mentioned or bool(reaction.get("treat_as_mention"))
    decision = AudiencePolicy(policy).evaluate(external_event, mentioned=effective_mentioned)
    if not decision.allowed:
        return _policy_denied_result(external_event, decision)
    if not reaction.get("fire", True):
        return {
            "status": "ignored",
            "assistant_text": "",
            "reason": str(reaction.get("reason") or "line hook did not trigger"),
            "event": external_event.as_dict(),
            "policy": decision.as_dict(),
            "reply": {"sent": False, "reason": "line hook trigger ignored"},
        }
    acknowledgement = _send_line_webhook_acknowledgement(event, endpoint=endpoint)
    runtime_context.setdefault("line_webhook_acknowledgement", acknowledgement)
    if _should_process_line_event_in_background(endpoint):
        return _with_line_acknowledgement(_dispatch_line_event_in_background(
            external_event,
            input_profile_id=endpoint.input_profile_id,
            audience_policy=policy,
            audience_decision=decision,
            context=runtime_context,
            mentioned=mentioned,
        ), acknowledgement)
    return _with_line_acknowledgement(_dispatch_line_event(
        external_event,
        input_profile_id=endpoint.input_profile_id,
        audience_policy=policy,
        audience_decision=decision,
        context=runtime_context,
        mentioned=mentioned,
    ), acknowledgement)


def _dispatch_line_event(
    external_event,
    *,
    input_profile_id: str,
    audience_policy: dict[str, Any],
    audience_decision,
    context: dict[str, Any],
    mentioned: bool = False,
) -> Dict[str, Any]:
    progress = _start_line_progress_notice(external_event, context)
    try:
        dispatch_kwargs = {
            "input_profile_id": input_profile_id,
            "audience_policy": audience_policy,
            "audience_decision": audience_decision,
            "context": context,
            "send_response": True,
            "mentioned": mentioned,
        }
        envelope_overrides = chat_link_envelope_overrides(context)
        if envelope_overrides:
            dispatch_kwargs["envelope_overrides"] = envelope_overrides
        result = dispatch_external_event(
            external_event,
            **dispatch_kwargs,
        )
        if result.get("status") == "error":
            reply = _send_line_error_notice(external_event, context=context)
            return {**result, "reply": reply}
        plan = result.get("response_plan") if isinstance(result.get("response_plan"), dict) else ResponsePlanner("line").plan(RumiResponse.from_result(result))
        reply = _send_response_plan(plan, external_event, context=context)
        return {**result, "reply": reply}
    except Exception as exc:
        _LOGGER.exception("LINE event processing failed")
        reply = _send_line_error_notice(external_event, context=context)
        return {
            "status": "error",
            "assistant_text": "",
            "error": {
                "code": "LINE_EVENT_PROCESSING_FAILED",
                "message": "LINE event processing failed",
                "detail": str(exc),
            },
            "event": external_event.as_dict(),
            "reply": reply,
        }
    finally:
        progress.cancel()


def _dispatch_line_event_in_background(
    external_event,
    *,
    input_profile_id: str,
    audience_policy: dict[str, Any],
    audience_decision,
    context: dict[str, Any],
    mentioned: bool = False,
) -> Dict[str, Any]:
    event_id = str((external_event.event or {}).get("id") or "").strip()
    background_context = dict(context or {})
    background_context["line_background_processing"] = True

    def worker() -> None:
        try:
            _dispatch_line_event(
                external_event,
                input_profile_id=input_profile_id,
                audience_policy=audience_policy,
                audience_decision=audience_decision,
                context=background_context,
                mentioned=mentioned,
            )
        except Exception:
            _send_line_error_notice(external_event, context=background_context)
            _LOGGER.exception("LINE background event processing failed event_id=%s", event_id or "<missing>")

    name_suffix = event_id or str(os.getpid())
    thread = threading.Thread(target=worker, name=f"line-webhook-{name_suffix}", daemon=True)
    thread.start()
    return {
        "status": "accepted",
        "assistant_text": "",
        "background_processing": True,
        "event_id": event_id,
        "event": external_event.as_dict(),
        "policy": audience_decision.as_dict() if hasattr(audience_decision, "as_dict") else audience_decision,
        "input_profile_id": input_profile_id,
        "reply": {"sent": False, "reason": "LINE event accepted for background processing"},
    }


def _send_response_plan(plan: dict[str, Any], external_event, *, context: dict[str, Any] | None = None) -> Dict[str, Any]:
    acknowledgement = context.get("line_webhook_acknowledgement") if isinstance(context, dict) else {}
    if isinstance(acknowledgement, dict) and acknowledgement.get("sent") is True:
        return {"sent": False, "reason": "LINE reply token already used for webhook acknowledgement"}
    action_plan = (plan.get("metadata") or {}).get("response_action_plan") if isinstance(plan.get("metadata"), dict) else {}
    if isinstance(action_plan, dict) and not action_plan.get("external_reply", True):
        return {"sent": False, "reason": "external reply suppressed by response prompt policy"}
    return LineResponseAdapter().send(plan, event=external_event, context=context)


def _send_line_error_notice(external_event, *, context: dict[str, Any] | None = None) -> Dict[str, Any]:
    notice_context = dict(context or {})
    notice_context["line_auto_post_on_reply_failure"] = True
    plan = {
        "provider": "line",
        "messages": [{"type": "text", "text": _LINE_SHORT_ERROR_TEXT}],
        "metadata": {"line_error_notice": True},
    }
    result = LineResponseAdapter().send(plan, event=external_event, context=notice_context)
    return {**result, "text": _LINE_SHORT_ERROR_TEXT}


class _ProgressNotice:
    def __init__(self, timer: threading.Timer | None) -> None:
        self._timer = timer

    def cancel(self) -> None:
        if self._timer is not None:
            self._timer.cancel()


def _start_line_progress_notice(external_event, context: dict[str, Any] | None) -> _ProgressNotice:
    context = context if isinstance(context, dict) else {}
    hook_settings = context.get("hook_settings") if isinstance(context.get("hook_settings"), dict) else {}
    if not _truthy(hook_settings.get("line_progress_post_enabled", True)):
        return _ProgressNotice(None)
    origin = origin_from_external_event(external_event)
    if not origin.can_push or not origin.source_id:
        return _ProgressNotice(None)
    if not (_truthy(context.get("line_auto_post_on_reply_failure")) or _truthy(context.get("allow_push")) or _source_record_allows_push(context)):
        return _ProgressNotice(None)
    delay = _clamped_int(hook_settings.get("line_progress_notice_seconds"), 40, 5, 55)

    def notify() -> None:
        try:
            LineResponseAdapter().send_text_push(origin.source_id, _LINE_LONG_TASK_NOTICE_TEXT)
        except Exception:
            _LOGGER.exception("LINE progress notice failed")

    timer = threading.Timer(delay, notify)
    timer.daemon = True
    timer.start()
    return _ProgressNotice(timer)


def _source_record_allows_push(context: dict[str, Any]) -> bool:
    record = context.get("source_record") if isinstance(context.get("source_record"), dict) else {}
    source = record.get("source") if isinstance(record.get("source"), dict) else record
    return bool(source.get("allow_push"))


def _handle_line_command(
    event: dict[str, Any],
    external_event,
    *,
    endpoint: WebhookEndpoint,
    context: dict[str, Any],
    hook_settings: dict[str, Any],
    audience_decision=None,
    audience_policy: dict[str, Any] | None = None,
) -> Dict[str, Any] | None:
    if not _line_slash_command_requested(event, hook_settings):
        return None
    text = _line_message_text(event)
    registry = SlashCommandRegistry()
    commands = registry.list_commands()
    parsed = _parse_line_slash_command(text, commands)
    if parsed is None:
        command_name = text[1:].strip().split(None, 1)[0] if text[1:].strip() else ""
        text_response = _line_unknown_command_text(command_name, commands)
        command_id = command_name
        arg_text = ""
    else:
        command = parsed["command"]
        command_id = str(command.get("id") or command.get("name") or "").strip()
        arg_text = str(parsed.get("arg_text") or "").strip()
        if command_id == "model":
            text_response = _line_model_command(endpoint, hook_settings, arg_text)
        elif command_id == "help":
            text_response = _line_help_text(commands)
        elif command_id == "status":
            text_response = _line_status_text(
                endpoint,
                hook_settings,
                context,
                external_event,
                commands=commands,
                audience_decision=audience_decision,
                audience_policy=audience_policy,
            )
        elif command_id in {"change", "newchat"}:
            command_text = f"/{command_id} {arg_text}".strip()
            chat_link_result = handle_chat_link_message(
                external_event,
                context,
                command_text,
                model=_line_response_model(endpoint, hook_settings),
            )
            text_response = str((chat_link_result or {}).get("assistant_text") or CHAT_LINK_PROMPT)
        else:
            args = _line_command_args(command, arg_text)
            result = registry.execute(
                {
                    "command": command.get("name") or command_id,
                    "args": args,
                    "mode": "chat",
                    "conversation_id": context.get("conversation_id"),
                },
                context,
            )
            text_response = _line_format_registry_command_result(command, result, args)
    plan = {"provider": "line", "messages": [{"type": "text", "text": text_response}], "metadata": {"line_command": command_id}}
    reply = _send_response_plan(plan, external_event, context=context)
    return {
        "status": "ok",
        "assistant_text": text_response,
        "line_command": {"name": command_id, "args": arg_text},
        "response_plan": plan,
        "reply": reply,
    }


def _line_slash_command_requested(event: dict[str, Any], hook_settings: dict[str, Any]) -> bool:
    if not _truthy(hook_settings.get("line_slash_commands_enabled", True)):
        return False
    text = _line_message_text(event)
    return text.startswith("/") and not text.startswith("//")


def _parse_line_slash_command(text: str, commands: list[dict[str, Any]]) -> dict[str, Any] | None:
    body = str(text or "").strip().lstrip("/").strip()
    if not body:
        return None
    candidates: list[tuple[int, dict[str, Any], str, str]] = []
    for command in commands:
        for name in _line_command_names(command):
            rest = _line_command_rest(body, name)
            if rest is not None:
                candidates.append((len(name), command, name, rest))
    if not candidates:
        return None
    _length, command, name, rest = sorted(candidates, key=lambda item: (-item[0], str(item[1].get("id") or "")))[0]
    return {"command": command, "matched_name": name, "arg_text": rest}


def _line_command_rest(body: str, name: str) -> str | None:
    parts = [part for part in re.split(r"[\s_-]+", str(name or "").strip().lower()) if part]
    if not parts:
        return None
    pattern = r"^" + r"[\s_-]+".join(re.escape(part) for part in parts) + r"(?:\s+|$)"
    match = re.match(pattern, str(body or "").strip(), flags=re.IGNORECASE)
    if match is None:
        return None
    return str(body or "").strip()[match.end():].strip()


def _line_command_names(command: dict[str, Any]) -> list[str]:
    names = [
        str(command.get("id") or "").strip().lower().lstrip("/"),
        str(command.get("name") or "").strip().lower().lstrip("/"),
    ]
    names.extend(str(alias or "").strip().lower().lstrip("/") for alias in command.get("aliases") or [])
    return sorted({name for name in names if name}, key=len, reverse=True)


def _line_command_args(command: dict[str, Any], arg_text: str) -> dict[str, Any]:
    specs = [spec for spec in command.get("args", []) if isinstance(spec, dict)]
    if not specs:
        return {}
    text = str(arg_text or "").strip()
    if not text:
        return {}
    if len(specs) == 1:
        return {str(specs[0].get("name") or "value"): text}

    args: dict[str, Any] = {}
    remaining = text
    for index, spec in enumerate(specs):
        name = str(spec.get("name") or "").strip()
        if not name:
            continue
        if index == len(specs) - 1 or spec.get("type") == "string":
            if remaining:
                args[name] = remaining
            break
        token, _sep, rest = remaining.partition(" ")
        if token:
            args[name] = token
        remaining = rest.strip()
    return args


def _line_model_status(endpoint: WebhookEndpoint, hook_settings: dict[str, Any]) -> str:
    answer_model = _line_response_model(endpoint, hook_settings) or "(未設定)"
    default_model = str(hook_settings.get("default_model") or "(未設定)")
    trigger_mode = str(hook_settings.get("response_trigger_mode") or "always")
    trigger_model = str(hook_settings.get("trigger_model") or "inherit")
    line_model = str(hook_settings.get("line_model") or "")
    lines = [
        f"応答モデル: {answer_model}",
        f"デフォルトモデル: {default_model}",
        f"反応モード: {trigger_mode}",
        f"判断モデル: {trigger_model}",
    ]
    if line_model:
        lines.append(f"LINE個別モデル: {line_model}")
    return "\n".join(lines)


def _line_model_command(endpoint: WebhookEndpoint, hook_settings: dict[str, Any], query: str) -> str:
    query = str(query or "").strip()
    if not query:
        return _line_model_status(endpoint, hook_settings)
    resolution = _resolve_line_model_query(query, limit=6)
    exact = resolution.get("exact") if isinstance(resolution, dict) else None
    candidates = resolution.get("candidates") if isinstance(resolution, dict) else []
    if isinstance(exact, dict) and exact.get("profile_id"):
        return _set_line_endpoint_model(endpoint, str(exact["profile_id"]), hook_settings)
    if candidates:
        return _line_model_candidates_text(query, candidates)
    return "一致するモデルが見つかりません。\n/model gpt のように短めに打つと候補を出します。"


def _line_change_command(external_event, context: dict[str, Any], arg_text: str) -> str:
    result = handle_chat_link_message(external_event, context, f"/change {arg_text}".strip())
    return str((result or {}).get("assistant_text") or CHAT_LINK_PROMPT)


def _line_chat_id_arg(arg_text: str) -> str:
    text = str(arg_text or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        text = text[1:-1].strip()
    return text


def _linked_line_conversation_id(context: dict[str, Any]) -> str:
    return chat_linked_conversation_id(context)


def _line_envelope_overrides(context: dict[str, Any]) -> dict[str, Any] | None:
    return chat_link_envelope_overrides(context)


def _line_context_source(context: dict[str, Any]) -> dict[str, Any]:
    record = context.get("source_record") if isinstance(context.get("source_record"), dict) else {}
    source = record.get("source") if isinstance(record.get("source"), dict) else record
    return source if isinstance(source, dict) else {}


def _set_line_endpoint_model(endpoint: WebhookEndpoint, model: str, hook_settings: dict[str, Any]) -> str:
    model = str(model or "").strip()
    if not model:
        return _line_model_status(endpoint, hook_settings)
    try:
        from domain.webhook.endpoint_store import WebhookEndpointStore

        payload = endpoint.as_dict(redact=False)
        conversation = dict(payload.get("conversation") if isinstance(payload.get("conversation"), dict) else {})
        conversation["model"] = model
        payload["conversation"] = conversation
        WebhookEndpointStore().upsert(payload)
        _persist_line_hook_model(model)
        hook_settings["line_model"] = model
        return f"LINE応答モデルを {model} にしました。"
    except Exception as exc:
        return f"モデル変更に失敗しました: {exc}"


def _resolve_line_model_query(query: str, *, limit: int = 6) -> dict[str, Any]:
    try:
        from domain.ai_client.model_runtime_settings import ModelRuntimeSettingsService

        service = ModelRuntimeSettingsService()
        override = os.environ.get("RUMI_DEFAULTSPACK_FRONTEND_SETTINGS_PATH", "").strip()
        if override:
            service._settings_path = Path(override)  # type: ignore[attr-defined]
        resolution = service.resolve_model_candidates(query, limit=limit)
    except Exception:
        resolution = {"query": query, "exact": None, "candidates": []}
    if resolution.get("exact") or resolution.get("candidates"):
        return resolution

    candidates = _fuzzy_line_model_candidates(query, limit=limit)
    return {"query": query, "exact": None, "candidates": candidates}


def _fuzzy_line_model_candidates(query: str, *, limit: int = 6) -> list[dict[str, Any]]:
    cleaned = _normalize_match_text(query)
    if not cleaned:
        return []
    try:
        from domain.ai_client.model_search import search_models

        models = search_models({"max_results": 100}).get("models", [])
    except Exception:
        models = []
    scored: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in models:
        if not isinstance(item, dict):
            continue
        profile_id = str(item.get("profile_id") or item.get("qualified_model_id") or "").strip()
        if not profile_id or profile_id in seen:
            continue
        fields = [
            item.get("profile_id"),
            item.get("qualified_model_id"),
            item.get("provider_id"),
            item.get("model_id"),
            item.get("display_name"),
            item.get("label"),
        ]
        score = max((SequenceMatcher(None, cleaned, _normalize_match_text(field)).ratio() for field in fields if str(field or "").strip()), default=0.0)
        if score < 0.46:
            continue
        candidate = dict(item)
        candidate["score"] = int(score * 100)
        scored.append(candidate)
        seen.add(profile_id)
    scored.sort(key=lambda item: (-int(item.get("score") or 0), str(item.get("label") or item.get("profile_id") or "").casefold()))
    return scored[:limit]


def _line_model_candidates_text(query: str, candidates: list[dict[str, Any]]) -> str:
    lines = [f"モデル候補: {query}"]
    for index, candidate in enumerate(candidates[:6], start=1):
        profile_id = str(candidate.get("profile_id") or candidate.get("qualified_model_id") or "").strip()
        label = str(candidate.get("label") or candidate.get("display_name") or profile_id).strip()
        status = "設定済み" if candidate.get("configured") else "未設定"
        if candidate.get("local"):
            status = "ローカル"
        lines.append(f"{index}. {profile_id} ({label}, {status})")
    lines.append("設定: /model <候補ID>")
    return "\n".join(lines)


def _persist_line_hook_model(model: str) -> None:
    path = _frontend_settings_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    hook = data.get("hook") if isinstance(data.get("hook"), dict) else {}
    hook["line_model"] = model
    data["hook"] = hook
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _frontend_settings_path() -> Path:
    override = os.environ.get("RUMI_DEFAULTSPACK_FRONTEND_SETTINGS_PATH", "").strip()
    return Path(override) if override else Path(__file__).resolve().parents[3] / "user_data" / "shared" / "frontend_settings.json"


def _line_help_text(commands: list[dict[str, Any]]) -> str:
    lines = ["使えるLINEコマンド:"]
    for command in commands:
        primary = str(command.get("name") or command.get("id") or "").strip()
        if not primary:
            continue
        aliases = [str(alias) for alias in command.get("aliases") or [] if str(alias or "").strip()]
        alias_text = f" ({', '.join('/' + alias for alias in aliases)})" if aliases else ""
        label = str(command.get("label") or "").strip()
        lines.append(f"/{primary}{alias_text} - {label}")
    lines.append("高リスク/画面操作系はLINEでは案内のみ返します。")
    return text_limit("\n".join(lines), 5000)


def _line_status_text(
    endpoint: WebhookEndpoint,
    hook_settings: dict[str, Any],
    context: dict[str, Any],
    external_event,
    *,
    commands: list[dict[str, Any]],
    audience_decision=None,
    audience_policy: dict[str, Any] | None = None,
) -> str:
    origin = origin_from_external_event(external_event)
    source_record = context.get("source_record") if isinstance(context.get("source_record"), dict) else {}
    source = source_record.get("source") if isinstance(source_record.get("source"), dict) else {}
    linked_chat_id = chat_linked_conversation_id(context)
    output = _frontend_external_output_settings()
    token_configured = _line_channel_access_token_configured()
    mention = external_event.metadata.get("line_mention") if isinstance(external_event.metadata, dict) else {}
    decision_text = "allow" if bool(getattr(audience_decision, "allowed", False)) else "deny"
    if hasattr(audience_decision, "reason"):
        decision_text += f" ({audience_decision.reason})"
    policy_default = str((audience_policy or {}).get("default") or "").strip() or "unknown"
    lines = [
        "LINE status",
        f"hook: {'on' if hook_settings.get('enabled') else 'off'}",
        f"slash commands: {'on' if hook_settings.get('line_slash_commands_enabled') else 'off'}",
        f"model: {_line_response_model(endpoint, hook_settings) or '(未設定)'}",
        f"default model: {hook_settings.get('default_model') or '(未設定)'}",
        f"line model: {hook_settings.get('line_model') or '(未設定)'}",
        f"answer model: {hook_settings.get('answer_model') or '(未設定)'}",
        f"trigger: {hook_settings.get('response_trigger_mode') or 'always'} / prefix {hook_settings.get('trigger_prefix') or '#'}",
        f"judge model: {hook_settings.get('trigger_model') or 'inherit'}",
        f"chatid: {linked_chat_id or '(default)'}",
        f"source: {origin.source_type} {_short_id(origin.source_id)}",
        f"source enabled: {'on' if source.get('enabled') else 'off'}",
        f"source push: {'on' if source.get('allow_push') else 'off'}",
        f"group mention required: {'on' if mention.get('require_group_mention') else 'off'}",
        f"mentioned: {'yes' if mention.get('mentioned') else 'no'}",
        f"policy: {decision_text}, default {policy_default}",
        f"send mode: {output.get('output_send_mode') or 'reply_to_origin'}",
        f"reply fallback: {'auto post' if hook_settings.get('line_auto_post_on_reply_failure') else 'ask/log'}",
        f"progress post: {'on' if hook_settings.get('line_progress_post_enabled') else 'off'}",
        f"LINE token: {'ok' if token_configured else 'missing'}",
        "image reply: HTTPS JPEG/PNG URLなら対応",
        f"commands: {len(commands)}",
    ]
    return "\n".join(lines)


def _line_channel_access_token_configured() -> bool:
    try:
        from domain.external.token_store import read_external_token

        return bool(read_external_token("line", kind="channel_access_token"))
    except Exception:
        return False


def _line_unknown_command_text(name: str, commands: list[dict[str, Any]]) -> str:
    suggestions = _line_command_suggestions(name, commands)
    if suggestions:
        return "コマンドが見つかりません。\n候補: " + ", ".join(f"/{item}" for item in suggestions)
    return "コマンドが見つかりません。/help で一覧を見られます。"


def _line_command_suggestions(name: str, commands: list[dict[str, Any]], *, limit: int = 5) -> list[str]:
    needle = _normalize_match_text(name)
    if not needle:
        return [str(command.get("name") or command.get("id")) for command in commands[:limit] if command.get("name") or command.get("id")]
    scored: list[tuple[float, str]] = []
    seen: set[str] = set()
    for command in commands:
        primary = str(command.get("name") or command.get("id") or "").strip()
        for candidate in _line_command_names(command):
            normalized = _normalize_match_text(candidate)
            if not normalized:
                continue
            score = SequenceMatcher(None, needle, normalized).ratio()
            if needle in normalized or normalized in needle:
                score += 0.35
            if score < 0.48:
                continue
            display = primary or candidate
            if display in seen:
                continue
            seen.add(display)
            scored.append((score, display))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [item[1] for item in scored[:limit]]


def _line_format_registry_command_result(command: dict[str, Any], result: dict[str, Any], args: dict[str, Any]) -> str:
    command_name = str(command.get("name") or command.get("id") or "").strip()
    if not isinstance(result, dict):
        return f"/{command_name}: 実行結果を読み取れませんでした。"
    if result.get("status") == "error":
        err = result.get("error") if isinstance(result.get("error"), dict) else {}
        code = str(err.get("code") or "ERROR")
        message = str(err.get("message") or "失敗しました")
        if code == "COMMAND_UNAVAILABLE":
            return f"/{command_name}: このコマンドはLINEのchatモードでは使えません。"
        return f"/{command_name}: {message}"
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    if data.get("requires_approval"):
        return f"/{command_name}: 承認センターが必要です。LINEからは実行せず、defaultspack画面で確認してください。"
    if data.get("executed"):
        return _line_executed_command_text(command_name, data.get("result"))
    action = str(data.get("action") or "").strip()
    if action:
        args_text = _line_args_text(args)
        suffix = f" args: {args_text}" if args_text else ""
        return f"/{command_name}: defaultspack画面用のコマンドです。action={action}{suffix}"
    return f"/{command_name}: 受け付けました。"


def _line_executed_command_text(command_name: str, result: Any) -> str:
    if isinstance(result, dict):
        if "level" in result:
            return f"/{command_name}: thinking={result.get('level')}"
        if "profile_id" in result:
            return f"/{command_name}: model={result.get('profile_id')}"
        compact = json.dumps(result, ensure_ascii=False, sort_keys=True)
        return text_limit(f"/{command_name}: {compact}", 5000)
    if result is None:
        return f"/{command_name}: 完了しました。"
    return text_limit(f"/{command_name}: {result}", 5000)


def _line_args_text(args: dict[str, Any]) -> str:
    if not args:
        return ""
    return ", ".join(f"{key}={value}" for key, value in args.items())


def _normalize_match_text(value: Any) -> str:
    return re.sub(r"[\s_-]+", " ", str(value or "").strip().casefold())


def _short_id(value: str) -> str:
    text = str(value or "").strip()
    if len(text) <= 12:
        return text or "(none)"
    return text[:6] + "..." + text[-4:]


def _line_reaction_decision(event: dict[str, Any], external_event, hook_settings: dict[str, Any]) -> dict[str, Any]:
    if not _truthy(hook_settings.get("enabled", True)):
        return {"fire": False, "reason": "hook disabled"}
    mode = str(hook_settings.get("response_trigger_mode") or "always").strip().lower()
    if mode == "always":
        return {"fire": True, "reason": mode}
    if mode == "auto":
        return {"fire": True, "reason": mode, "treat_as_mention": True}
    if mode != "prefix":
        return {"fire": True, "reason": "unknown mode fallback"}
    text = _line_message_text(event)
    prefix = str(hook_settings.get("trigger_prefix") or "#").strip() or "#"
    if not text.startswith(prefix):
        return {"fire": False, "reason": f"missing trigger prefix {prefix}"}
    stripped = text[len(prefix):].strip()
    if stripped:
        _set_line_message_text(external_event, stripped)
    return {"fire": True, "reason": "trigger prefix matched", "treat_as_mention": True}


def _line_message_text(event: dict[str, Any]) -> str:
    message = event.get("message") if isinstance(event.get("message"), dict) else {}
    return str(message.get("text") or "").strip()


def _set_line_message_text(external_event, text: str) -> None:
    for container in (
        external_event.payload.get("message") if isinstance(external_event.payload, dict) else None,
        external_event.metadata.get("message") if isinstance(external_event.metadata, dict) else None,
    ):
        if isinstance(container, dict):
            container["text"] = text


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
    path = Path(override) if override else Path(__file__).resolve().parents[3] / "user_data" / "shared" / "frontend_settings.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    output = data.get("external_output") if isinstance(data.get("external_output"), dict) else {}
    return dict(output)


def _frontend_hook_settings() -> dict[str, Any]:
    override = os.environ.get("RUMI_DEFAULTSPACK_FRONTEND_SETTINGS_PATH", "").strip()
    path = Path(override) if override else Path(__file__).resolve().parents[3] / "user_data" / "shared" / "frontend_settings.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    hook = data.get("hook") if isinstance(data.get("hook"), dict) else {}
    external_output = data.get("external_output") if isinstance(data.get("external_output"), dict) else {}
    triggers = data.get("triggers") if isinstance(data.get("triggers"), dict) else {}
    models = data.get("models") if isinstance(data.get("models"), dict) else {}
    mode = str(hook.get("response_trigger_mode") or hook.get("trigger_mode") or "always").strip().lower()
    if mode in {"ai", "llm"}:
        mode = "auto"
    if mode not in {"always", "prefix", "auto"}:
        mode = "always"
    return {
        "enabled": _truthy(hook.get("enabled", True)),
        "response_trigger_mode": mode,
        "trigger_prefix": str(hook.get("trigger_prefix") or "#").strip() or "#",
        "trigger_model": str(hook.get("trigger_model") or triggers.get("model") or "").strip(),
        "answer_model": str(hook.get("answer_model") or hook.get("default_answer_model") or "").strip(),
        "line_model": str(hook.get("line_model") or hook.get("line_default_model") or "").strip(),
        "default_model": str(models.get("preferred_model") or "").strip(),
        "line_auto_post_on_reply_failure": _truthy(
            hook.get("line_auto_post_on_reply_failure")
            or hook.get("auto_post_on_reply_failure")
            or external_output.get("line_auto_post_on_reply_failure")
        ),
        "line_progress_post_enabled": _truthy(hook.get("line_progress_post_enabled", True)),
        "line_progress_notice_seconds": _clamped_int(hook.get("line_progress_notice_seconds"), 40, 5, 55),
        "line_slash_commands_enabled": _truthy(hook.get("line_slash_commands_enabled", True)),
        "line_reply_guidance_prompt_enabled": _truthy(hook.get("line_reply_guidance_prompt_enabled", True)),
    }


def _line_response_model(endpoint: WebhookEndpoint, hook_settings: dict[str, Any] | None = None) -> str:
    hook_settings = hook_settings if isinstance(hook_settings, dict) else {}
    return str(
        hook_settings.get("line_model")
        or hook_settings.get("answer_model")
        or endpoint.conversation.get("model")
        or hook_settings.get("default_model")
        or ""
    ).strip()


def _apply_hook_context(runtime_context: dict[str, Any], hook_settings: dict[str, Any], *, endpoint: WebhookEndpoint) -> None:
    runtime_context.setdefault("hook_settings", dict(hook_settings))
    if hook_settings.get("line_auto_post_on_reply_failure"):
        runtime_context.setdefault("line_auto_post_on_reply_failure", True)
    response = endpoint.response if isinstance(endpoint.response, dict) else {}
    response_mode = str(response.get("mode") or "").strip().lower()
    if (
        hook_settings.get("line_reply_guidance_prompt_enabled")
        and response_mode not in {"computer_use_line_biz", "computer_use_only"}
        and not str(runtime_context.get("external_prompt_prefix") or "").strip()
    ):
        _append_prompt_prefix(runtime_context, _LINE_REPLY_GUIDANCE_PROMPT)
    if str(hook_settings.get("response_trigger_mode") or "") == "auto":
        trigger_model = str(hook_settings.get("trigger_model") or hook_settings.get("answer_model") or endpoint.conversation.get("model") or "").strip()
        runtime_context["trigger_decision_config"] = {
            "enabled": True,
            "mode": "llm",
            "default_action": "ignore",
            "fallback_action": "ignore",
            "filter_unrelated": True,
            "llm": {
                "model": trigger_model or "inherit",
                "system_prompt": (
                    "Decide if this LINE message is asking this bot to answer. "
                    "Return JSON: action fire or ignore, send_response boolean, reason."
                ),
            },
        }
        runtime_context["trigger_decision_llm"] = _line_trigger_llm_client(trigger_model)


def _append_prompt_prefix(runtime_context: dict[str, Any], text: str) -> None:
    prompt = str(text or "").strip()
    if not prompt:
        return
    current = str(runtime_context.get("external_prompt_prefix") or "").strip()
    runtime_context["external_prompt_prefix"] = f"{current}\n{prompt}".strip() if current else prompt


def _line_trigger_llm_client(model: str):
    def decide(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            from domain.ai_client.client import AIClient

            selected_model = str(model or payload.get("model") or "").strip()
            if selected_model == "inherit":
                selected_model = ""
            if not selected_model:
                from domain.ai_client.model_runtime_settings import ModelRuntimeSettingsService

                selected_model = ModelRuntimeSettingsService().get_preferred_model()
            response = AIClient().complete(
                selected_model,
                payload.get("messages") if isinstance(payload.get("messages"), list) else [],
                [],
                {"temperature": 0, "response_format": {"type": "json_object"}},
            )
            return response
        except Exception as exc:  # fail open so LINE does not silently miss users when the judge model is unavailable
            return {"action": "fire", "send_response": True, "reason": f"auto trigger model unavailable: {exc}"}

    return decide


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


def _send_line_webhook_acknowledgement(event: dict[str, Any], *, endpoint: WebhookEndpoint) -> Dict[str, Any]:
    if not _line_webhook_ack_enabled(endpoint):
        return {"sent": False, "reason": "LINE webhook acknowledgement disabled"}
    reply_token = str(event.get("replyToken") or "").strip()
    if not reply_token:
        return {"sent": False, "reason": "missing reply token"}
    result = _send_line_reply(reply_token, _LINE_WEBHOOK_ACK_TEXT)
    return {
        **result,
        "text": _LINE_WEBHOOK_ACK_TEXT,
    }


def _with_line_acknowledgement(result: Dict[str, Any], acknowledgement: dict[str, Any]) -> Dict[str, Any]:
    return {**result, "acknowledgement": acknowledgement}


def _line_webhook_ack_enabled(endpoint: WebhookEndpoint) -> bool:
    response = endpoint.response if isinstance(endpoint.response, dict) else {}
    mode = str(response.get("mode") or "").strip().lower()
    if mode != "computer_use_line_biz":
        return False
    configured = None
    for key in ("reply_on_receive", "acknowledge_on_receive", "send_webhook_acknowledgement"):
        if key in response:
            configured = response.get(key)
            break
    return True if configured is None else _truthy(configured)


def _apply_endpoint_response_context(runtime_context: dict[str, Any], endpoint: WebhookEndpoint) -> dict[str, Any]:
    updated = dict(runtime_context or {})
    response = endpoint.response if isinstance(endpoint.response, dict) else {}
    if not response:
        return updated

    mode = str(response.get("mode") or "").strip().lower()
    history_mode = str(
        response.get("chat_history_mode")
        or response.get("external_chat_history_mode")
        or ""
    ).strip().lower()
    if history_mode:
        updated.setdefault("external_chat_history_mode", history_mode)
    elif mode == "computer_use_line_biz":
        updated.setdefault("external_chat_history_mode", "current_turn")

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
        or ("LINE Chat" if mode == "computer_use_line_biz" else "")
        or ""
    ).strip()
    if target_title:
        updated.setdefault("computer_use_target_title", target_title)
    if mode == "computer_use_line_biz":
        updated.setdefault("computer_use_physical_clicks", True)
        updated.setdefault("computer_use_reply_surface", "line_biz")

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


def _should_process_line_event_in_background(endpoint: WebhookEndpoint) -> bool:
    response = endpoint.response if isinstance(endpoint.response, dict) else {}
    if not response:
        return False
    mode = str(response.get("mode") or "").strip().lower()
    if mode != "computer_use_line_biz":
        return False
    return any(
        _truthy(response.get(key))
        for key in ("background_processing", "async_processing", "run_in_background")
    )


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
        "Before using any tools, decide the exact reply text from the external source message in this prompt. "
        "If the source message says to reply exactly with some text, send exactly that text and nothing else. "
        "Treat the visible LINE Biz chat history only as the destination UI; it can be stale or unrelated to this webhook event. "
        "Do not inspect, reread, or scroll visible chat bubbles to understand the customer request. "
        "Start by checking computer.windows, and if a visible Google Chrome LINE window exists, "
        "target it with computer.select_window before screenshots or clicks. "
        "This Windows workflow only works against a visible desktop Chrome window, so if Chrome is "
        "not visible return a short local note asking for the LINE Biz window to be opened on screen. "
        "The external source message below is already the customer message you should answer. "
        "Before typing, pressing Enter, or sending, call computer.context or inspect active_window in the latest "
        "screenshot result to confirm the foreground window is the Chrome LINE chat; if Codex or another app is frontmost, "
        "refocus the LINE window with computer.select_window before continuing. "
        "After the target chat is visible, use screenshots only to locate the reply composer or send control near the bottom of the chat pane. "
        "If the reply composer is hidden, scroll toward the bottom once and click the large red circular reply button near the lower edge to open it. "
        "Any click that must affect LINE Biz must be a physical foreground click: call computer.click with physical=true. "
        "A normal computer.click is only a virtual cursor marker and will not open the composer or press Send. "
        "Do not use Ctrl+A or select existing chat text. "
        "If the exact reply text is already visible in the composer, do not type it again. "
        "To send, click the left green Send button labeled 送信, not the small dropdown arrow on its right. "
        "Do not keep scrolling through the transcript repeatedly; after one bottom scroll, use a physical click to focus the composer/reply button. "
        "Then answer the external source message clearly, "
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


def _clamped_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _line_message_mentions_bot(event: dict[str, Any], *, destination: str = "") -> bool:
    message = event.get("message") if isinstance(event.get("message"), dict) else {}
    mention = message.get("mention") if isinstance(message.get("mention"), dict) else {}
    mentionees = mention.get("mentionees") if isinstance(mention.get("mentionees"), list) else []
    destination_id = str(destination or "").strip()
    for item in mentionees:
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip() != "user":
            continue
        if bool(item.get("isSelf")):
            return True
        if destination_id and str(item.get("userId") or "").strip() == destination_id:
            return True
    return False


def _require_line_group_mention(endpoint: WebhookEndpoint, external_event) -> bool:
    if getattr(external_event, "scope", None) is None or external_event.scope.type not in {"group", "room"}:
        return False
    response = endpoint.response if isinstance(endpoint.response, dict) else {}
    conversation = endpoint.conversation if isinstance(endpoint.conversation, dict) else {}
    metadata = endpoint.metadata if isinstance(endpoint.metadata, dict) else {}
    configured = None
    for container in (metadata, response, conversation):
        for key in ("require_group_mention", "group_mention_only", "mention_only_in_groups", "group_room_mention_required"):
            if key in container:
                configured = container.get(key)
                break
        if configured is not None:
            break
    if configured is None:
        configured = _line_mention_policy_default()
    if configured is None:
        configured = True
    return _truthy(configured)


def _line_mention_policy_default() -> Any:
    try:
        data = json.loads(_frontend_settings_path().read_text(encoding="utf-8"))
    except Exception:
        return True
    if not isinstance(data, dict):
        return True
    line_settings = data.get("line") if isinstance(data.get("line"), dict) else {}
    policy = line_settings.get("mention_policy")
    if isinstance(policy, dict):
        for key in ("group_room_mention_required", "require_group_mention", "groups_require_mention"):
            if key in policy:
                return policy.get(key)
    if policy is not None:
        text = str(policy).strip().lower()
        if text in {"mention_required", "groups_only", "group_room", "true", "on", "1"}:
            return True
        if text in {"always", "all", "false", "off", "0"}:
            return False
    return True


def _require_audience_mention(policy: dict[str, Any]) -> dict[str, Any]:
    updated = dict(policy or {})
    require = dict(updated.get("require") if isinstance(updated.get("require"), dict) else {})
    require["mention"] = True
    updated["require"] = require
    return updated


def _allow_current_scope(policy: dict[str, Any], external_event) -> dict[str, Any]:
    scope = getattr(external_event, "scope", None)
    if scope is None or scope.type not in {"group", "room"} or not scope.id:
        return dict(policy or {})
    updated = dict(policy or {})
    allow = list(updated.get("allow")) if isinstance(updated.get("allow"), list) else []
    scope_rule = {
        "id": f"mentioned-scope:{scope.type}:{scope.id}",
        "provider": external_event.provider,
        "scope": {"type": scope.type, "id": scope.id},
    }
    if not any(
        isinstance(rule, dict)
        and rule.get("provider") == scope_rule["provider"]
        and isinstance(rule.get("scope"), dict)
        and str(rule["scope"].get("type") or "") == scope.type
        and str(rule["scope"].get("id") or "") == scope.id
        for rule in allow
    ):
        allow.append(scope_rule)
    updated["allow"] = allow
    return updated


def _allow_current_source(policy: dict[str, Any], external_event) -> dict[str, Any]:
    origin = origin_from_external_event(external_event)
    if not origin.source_id:
        return dict(policy or {})
    updated = dict(policy or {})
    allow = list(updated.get("allow")) if isinstance(updated.get("allow"), list) else []
    scope_rule = {
        "id": f"line-command-source:{origin.source_type}:{origin.source_id}",
        "provider": origin.provider,
        "scope": {"type": origin.source_type, "id": origin.source_id},
    }
    if not any(
        isinstance(rule, dict)
        and rule.get("provider") == scope_rule["provider"]
        and isinstance(rule.get("scope"), dict)
        and str(rule["scope"].get("type") or "") == origin.source_type
        and str(rule["scope"].get("id") or "") == origin.source_id
        for rule in allow
    ):
        allow.append(scope_rule)
    updated["allow"] = allow
    return updated
